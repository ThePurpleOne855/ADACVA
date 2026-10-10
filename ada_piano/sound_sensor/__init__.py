"""MIDI note input. MIDI measures key events, not microphone audio."""

from dataclasses import dataclass
from collections.abc import Iterable, Iterator
from time import monotonic
from queue import Queue, Empty


@dataclass(frozen=True)
class NoteEvent:
    note: int
    velocity: int
    timestamp: float
    source: str
    kind: str = "note_on"
    channel: int = 0


def simulated_notes(notes: Iterable[int], *, releases: bool = False) -> Iterator[NoteEvent]:
    for note in notes:
        yield NoteEvent(note, 80, monotonic(), "simulation")
        if releases:
            yield NoteEvent(note, 0, monotonic(), "simulation", "note_off")


def simulated_chords(chords: Iterable[Iterable[int]], spacing: float = 0.03) -> Iterator[NoteEvent]:
    """Deterministic event timestamps; no real-time sleeps or device required."""
    timestamp = 0.0
    for chord in chords:
        pitches = tuple(chord)
        for i, pitch in enumerate(pitches):
            yield NoteEvent(pitch, 80, timestamp + i * spacing, "simulation")
        timestamp += max(0.5, len(pitches) * spacing + 0.1)
        for pitch in pitches:
            yield NoteEvent(pitch, 0, timestamp, "simulation", "note_off")
        timestamp += 0.1


def _mido():
    try:
        import mido
        import rtmidi  # noqa: F401 - check native backend before opening a port
    except ImportError as exc:
        raise RuntimeError('MIDI dependencies missing. Run: uv sync --extra midi') from exc
    mido.set_backend("mido.backends.rtmidi")
    return mido


def list_ports() -> list[str]:
    return _mido().get_input_names()


def event_from_message(message) -> NoteEvent | None:
    if message.type not in {"note_on", "note_off"}:
        return None
    kind = "note_off" if message.type == "note_off" or message.velocity == 0 else "note_on"
    return NoteEvent(message.note, message.velocity, monotonic(), "midi", kind,
                     getattr(message, "channel", 0))


def midi_notes(port_name: str) -> Iterator[NoteEvent]:
    mido = _mido()
    pending = Queue()

    def receive(message):
        # Timestamp when the backend delivers input, even during spoken feedback.
        event = event_from_message(message)
        if event is not None:
            pending.put(event)

    with mido.open_input(port_name, callback=receive):
        while True:
            try:
                event = pending.get(timeout=0.2)
            except Empty:
                continue
            yield event
