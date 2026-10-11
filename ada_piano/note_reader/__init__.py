"""Independent MIDI input and key state for the Note Reader GUI.

MIDI and GUI dependencies are loaded only when needed. Channels are displayed
as 1–16; held keys mean physical key presses, not notes prolonged by sustain.
"""

from collections import deque
from dataclasses import dataclass
from time import monotonic

from ada_piano.music_sheet import note_name


@dataclass(frozen=True)
class NoteEvent:
    kind: str
    note: int
    velocity: int
    channel: int
    timestamp: float
    duration: float | None = None

    @property
    def name(self) -> str:
        return note_name(self.note)


class NoteState:
    def __init__(self):
        self.held: dict[tuple[int, int], int] = {}
        self.sustain: set[int] = set()
        self.note_count = 0
        self._pressed_at: dict[tuple[int, int], float] = {}

    def reset(self):
        self.held.clear()
        self.sustain.clear()
        self.note_count = 0
        self._pressed_at.clear()

    def consume(self, message, timestamp: float | None = None) -> NoteEvent | None:
        if message.type == "reset":
            self.reset()
        elif message.type == "control_change":
            channel = message.channel + 1
            if message.control == 64:
                if message.value >= 64:
                    self.sustain.add(channel)
                else:
                    self.sustain.discard(channel)
            elif message.control in (120, 123):
                self.held = {key: value for key, value in self.held.items() if key[0] != channel}
                self._pressed_at = {key: value for key, value in self._pressed_at.items() if key[0] != channel}
            elif message.control == 121:
                self.sustain.discard(channel)
        elif message.type in ("note_on", "note_off"):
            channel = message.channel + 1
            pressed = message.type == "note_on" and message.velocity > 0
            key = (channel, message.note)
            if timestamp is None:
                timestamp = monotonic()
            duration = None
            if pressed:
                self.held[key] = message.velocity
                # A repeated press on the same pitch/channel starts a new timer.
                self._pressed_at[key] = timestamp
                self.note_count += 1
            else:
                self.held.pop(key, None)
                started = self._pressed_at.pop(key, None)
                if started is not None:
                    duration = timestamp - started
            return NoteEvent("on" if pressed else "off", message.note,
                             message.velocity, channel, timestamp, duration)
        return None


class NoteReader:
    """Nonblocking reader. Call all methods from one thread (the GUI thread).

    An optional backend allows tests to exercise connection handling without
    hardware. Production explicitly selects Mido's python-rtmidi backend, whose
    callback timestamps each message on arrival; poll() only drains them, so
    GUI or speech delays do not distort timing.
    """

    def __init__(self, backend=None):
        self._backend = backend
        self._port = None
        self.port_name: str | None = None
        self.state = NoteState()
        self.message_count = 0
        self.last_message: str | None = None
        self.last_received: float | None = None
        self.connected_at: float | None = None
        self._arrivals = deque()
        self._callback = False

    def _receive(self, message):
        # Runs on the backend thread; deque appends are thread-safe.
        self._arrivals.append((monotonic(), message))

    def _get_backend(self):
        if self._backend is None:
            try:
                import mido
                import rtmidi  # noqa: F401
            except ImportError as exc:
                raise RuntimeError("Install MIDI dependencies: uv sync --extra midi") from exc
            self._backend = mido.Backend("mido.backends.rtmidi")
        return self._backend

    @property
    def connected(self) -> bool:
        return self._port is not None

    def list_ports(self) -> list[str]:
        return self._get_backend().get_input_names()

    def connect(self, port_name: str):
        if not port_name:
            raise ValueError("Select a MIDI input first.")
        self.disconnect()
        if port_name not in self.list_ports():
            raise RuntimeError("That MIDI input is unavailable. Refresh inputs and select it again.")
        self._arrivals.clear()
        self._port = self._get_backend().open_input(port_name)
        self._callback = isinstance(getattr(type(self._port), "callback", None), property)
        if self._callback:
            self._port.callback = self._receive
        self.port_name = port_name
        self.connected_at = monotonic()

    def disconnect(self):
        port, self._port = self._port, None
        self.port_name = None
        self.state.reset()
        self.message_count = 0
        self.last_message = None
        self.last_received = None
        self.connected_at = None
        self._callback = False
        self._arrivals.clear()
        if port is not None:
            port.close()

    def check_connection(self):
        # RtMidi does not necessarily mark an unplugged ALSA port as closed.
        if self.connected and (self._port.closed or self.port_name not in self.list_ports()):
            self.disconnect()
            raise RuntimeError("MIDI input disconnected. Reconnect the cable, refresh inputs, and connect.")

    def poll(self, limit: int = 256) -> list[NoteEvent]:
        events = []
        if self._port is None:
            return events
        try:
            if self._port.closed:
                raise RuntimeError("MIDI input closed. Refresh inputs and reconnect.")
            # Limit work per GUI tick, including non-note messages such as clocks.
            for _ in range(limit):
                if self._callback:
                    if not self._arrivals:
                        break
                    received, message = self._arrivals.popleft()
                else:
                    message = self._port.poll()
                    if message is None:
                        break
                    received = monotonic()
                self.message_count += 1
                self.last_message = message.type
                self.last_received = received
                event = self.state.consume(message, received)
                if event is not None:
                    events.append(event)
        except Exception:
            self.disconnect()
            raise
        return events
