"""MIDI note input. MIDI measures key events, not microphone audio."""

from dataclasses import dataclass
from collections.abc import Iterable, Iterator
from time import monotonic


@dataclass(frozen=True)
class NoteEvent:
    note: int
    velocity: int
    timestamp: float
    source: str


def simulated_notes(notes: Iterable[int]) -> Iterator[NoteEvent]:
    for note in notes:
        yield NoteEvent(note, 80, monotonic(), "simulation")


def _mido():
    try:
        import mido
        import rtmidi  # noqa: F401 - check native backend before opening a port
    except ImportError as exc:
        raise RuntimeError('MIDI dependencies missing. Run: python -m pip install -e ".[midi]"') from exc
    mido.set_backend("mido.backends.rtmidi")
    return mido


def list_ports() -> list[str]:
    return _mido().get_input_names()


def event_from_message(message) -> NoteEvent | None:
    # A note_on with zero velocity is a release, not another played note.
    if message.type != "note_on" or message.velocity == 0:
        return None
    return NoteEvent(message.note, message.velocity, monotonic(), "midi")


def midi_notes(port_name: str) -> Iterator[NoteEvent]:
    mido = _mido()
    with mido.open_input(port_name) as port:
        for message in port:
            event = event_from_message(message)
            if event is not None:
                yield event
