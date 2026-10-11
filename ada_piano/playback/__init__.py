"""Bounded, nonblocking MIDI reference playback for GUI and future AI callers.

Public channels are 1–16. Beat positions use quarter-note beats. No GUI, AI SDK,
or score importer is required; callers supply a reviewed, explicit note plan.
"""

from collections import deque
from dataclasses import dataclass
import math
import re
from threading import Event, Lock, Thread
from time import monotonic


@dataclass(frozen=True)
class PlaybackNote:
    note: int
    start_beat: float = 0
    duration_beats: float = 1
    velocity: int = 70
    channel: int = 1


@dataclass(frozen=True)
class PlaybackEvent:
    kind: str
    note: int
    velocity: int
    channel: int
    timestamp: float
    duration: float | None = None
    source: str = "reference"


@dataclass(frozen=True)
class PlaybackStatus:
    state: str
    detail: str


def parse_note(text: str) -> int:
    """Accept MIDI integers or scientific pitches such as C4, F#4, Bb3."""
    text = text.strip()
    if re.fullmatch(r"\d{1,3}", text):
        value = int(text)
    else:
        match = re.fullmatch(r"([A-Ga-g])([#b♯♭]?)(-?\d)", text)
        if not match:
            raise ValueError(f"Invalid note {text!r}. Use C4, F#4, Bb3, or a MIDI number (0–127).")
        letter, accidental, octave = match.groups()
        value = (int(octave) + 1) * 12 + {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}[letter.upper()]
        value += {"": 0, "#": 1, "♯": 1, "b": -1, "♭": -1}[accidental]
    if not 0 <= value <= 127:
        raise ValueError("Notes must be in MIDI range 0–127 (C-1 to G9).")
    return value


def _number(value, label, minimum, maximum):
    if type(value) not in (int, float) or not math.isfinite(value) or not minimum <= value <= maximum:
        raise ValueError(f"{label} must be a finite number from {minimum} to {maximum}.")


def validate_notes(notes, tempo):
    _number(tempo, "Tempo", 20, 300)
    if not isinstance(notes, (list, tuple)) or not 1 <= len(notes) <= 4096:
        raise ValueError("Provide between 1 and 4096 notes.")
    intervals = {}
    for note in notes:
        if not isinstance(note, PlaybackNote):
            raise ValueError("Each note must be a PlaybackNote.")
        for value, label, lower, upper in ((note.note, "Pitch", 0, 127),
                                           (note.velocity, "Velocity", 1, 127),
                                           (note.channel, "Channel", 1, 16)):
            if type(value) is not int or not lower <= value <= upper:
                raise ValueError(f"{label} must be an integer from {lower} to {upper}.")
        _number(note.start_beat, "Start beat", 0, 1500)
        _number(note.duration_beats, "Duration in beats", 0.01, 1500)
        end = note.start_beat + note.duration_beats
        if end * 60 / tempo > 300:
            raise ValueError("A reference may be at most five minutes long.")
        intervals.setdefault((note.channel, note.note), []).append((note.start_beat, end))
    for spans in intervals.values():
        spans.sort()
        if any(end > following for (_, end), (following, _) in zip(spans, spans[1:])):
            raise ValueError("Overlapping notes of the same pitch/channel are ambiguous. Merge ties first.")
    return tuple(notes)


class ReferencePlayer:
    """One output worker owns each port from open through cleanup.

    list_ports(), play_notes(), play_request(), stop(), status, and drain_events()
    are safe for UI/controller callers. Only the worker sends MIDI. An injected
    backend/message factory allows tests without optional MIDI dependencies.
    """

    def __init__(self, backend=None, message_factory=None):
        self._backend = backend
        self._message_factory = message_factory
        self._backend_lock = Lock()
        self._control_lock = Lock()
        self._state_lock = Lock()
        self._stop = Event()
        self._thread = None
        self._closed = False
        self._events = deque(maxlen=8192)
        self._status = PlaybackStatus("idle", "Choose a MIDI output to play through the Yamaha.")

    def _get_backend(self):
        if self._backend is None:
            try:
                import mido
                import rtmidi  # noqa: F401
            except ImportError as exc:
                raise RuntimeError("Install MIDI support: uv sync --extra midi") from exc
            self._backend = mido.Backend("mido.backends.rtmidi")
        return self._backend

    def _message(self, kind, **values):
        if self._message_factory is None:
            import mido
            return mido.Message(kind, **values)
        return self._message_factory(kind, **values)

    def list_ports(self):
        with self._backend_lock:
            return self._get_backend().get_output_names()

    @property
    def status(self):
        with self._state_lock:
            return self._status

    def _set_status(self, state, detail):
        with self._state_lock:
            self._status = PlaybackStatus(state, detail)

    def drain_events(self):
        with self._state_lock:
            events = list(self._events)
            self._events.clear()
            return events

    def _emit(self, event):
        with self._state_lock:
            self._events.append(event)

    def play_request(self, request: dict, *, port_name: str):
        """JSON-compatible boundary for future AI commands.

        The application supplies the approved output; the request contains only
        {"tempo": 90, "notes": [{"note": 60, "start_beat": 0,
        "duration_beats": 1, "velocity": 70, "channel": 1}]}.
        Validation completes before any MIDI is sent.
        """
        if not isinstance(request, dict) or set(request) - {"tempo", "notes"}:
            raise ValueError("Playback requests accept only tempo and notes.")
        records = request.get("notes")
        if not isinstance(records, list) or not 1 <= len(records) <= 4096:
            raise ValueError("Provide between 1 and 4096 note objects.")
        try:
            notes = [PlaybackNote(**record) for record in records]
        except TypeError as exc:
            raise ValueError("Each note needs a note number and only supported note fields.") from exc
        self.play_notes(notes, port_name=port_name, tempo=request.get("tempo", 90))

    def play_notes(self, notes, *, port_name: str, tempo: float = 90):
        notes = validate_notes(notes, tempo)
        if not isinstance(port_name, str) or not port_name.strip():
            raise ValueError("Select a MIDI output first.")
        with self._control_lock:
            if self._closed:
                raise RuntimeError("This player has been closed.")
            if self._thread is not None and self._thread.is_alive():
                raise RuntimeError("Reference is playing. Stop it before starting another.")
            self._stop.clear()
            self._set_status("playing", f"Sending reference to {port_name}")
            self._thread = Thread(target=self._run, args=(notes, port_name, tempo), daemon=True)
            self._thread.start()

    def stop(self):
        with self._control_lock:
            if self._thread is not None and self._thread.is_alive():
                self._stop.set()

    def close(self):
        with self._control_lock:
            self._closed = True
            self._stop.set()
            thread = self._thread
        if thread is not None:
            thread.join(timeout=2)
            if thread.is_alive():
                raise RuntimeError("MIDI output did not stop within two seconds.")

    def _run(self, notes, port_name, tempo):
        port = None
        active = {}
        channels = sorted({note.channel - 1 for note in notes})
        error = None
        try:
            with self._backend_lock:
                backend = self._get_backend()
                if port_name not in backend.get_output_names():
                    raise RuntimeError("MIDI output unavailable. Refresh outputs and select it again.")
                port = backend.open_output(port_name)
            for channel in channels:
                if self._stop.is_set():
                    break
                port.send(self._message("control_change", channel=channel, control=64, value=0))
                port.send(self._message("program_change", channel=channel, program=0))
            schedule = []
            for note in notes:
                schedule.append((note.start_beat * 60 / tempo, 1, note))
                schedule.append(((note.start_beat + note.duration_beats) * 60 / tempo, 0, note))
            # Releases precede presses at a shared boundary (repeated notes).
            schedule.sort(key=lambda item: (item[0], item[1]))
            started = monotonic()
            next_check = started + 0.5
            for delay, pressed, note in schedule:
                while not self._stop.is_set():
                    now = monotonic()
                    if now >= next_check:
                        if port_name not in self.list_ports():
                            raise RuntimeError("MIDI output disconnected. Reconnect and refresh outputs.")
                        next_check = now + 0.5
                    remaining = started + delay - now
                    if remaining <= 0:
                        break
                    self._stop.wait(min(remaining, 0.1))
                if self._stop.is_set():
                    break
                key = (note.channel - 1, note.note)
                timestamp = monotonic()
                if pressed:
                    # Track before sending so cleanup also covers a partial send failure.
                    active[key] = timestamp
                    port.send(self._message("note_on", channel=key[0], note=key[1], velocity=note.velocity))
                    self._emit(PlaybackEvent("on", note.note, note.velocity, note.channel, timestamp))
                else:
                    port.send(self._message("note_off", channel=key[0], note=key[1], velocity=0))
                    duration = timestamp - active.pop(key)
                    self._emit(PlaybackEvent("off", note.note, 0, note.channel, timestamp, duration))
        except Exception as exc:
            error = str(exc)
        finally:
            if port is not None:
                for (channel, pitch), pressed_at in list(active.items()):
                    try:
                        port.send(self._message("note_off", channel=channel, note=pitch, velocity=0))
                        timestamp = monotonic()
                        self._emit(PlaybackEvent("off", pitch, 0, channel + 1, timestamp, timestamp - pressed_at))
                    except Exception as exc:
                        error = error or str(exc)
                for channel in channels:
                    try:
                        port.send(self._message("control_change", channel=channel, control=64, value=0))
                    except Exception as exc:
                        error = error or str(exc)
                try:
                    with self._backend_lock:
                        port.close()
                except Exception as exc:
                    error = error or str(exc)
            if error:
                self._set_status("error", f"Output error: {error}. If a note remains sounding, reconnect the interface and use the piano controls.")
            elif self._stop.is_set():
                self._set_status("stopped", "Reference stopped; playback notes released.")
            else:
                self._set_status("finished", "Reference sent. Your turn to play.")
