"""Structured exercises; score image recognition is outside the first prototype."""

from dataclasses import dataclass
from fractions import Fraction
import json
from pathlib import Path


def note_name(note: int) -> str:
    names = ("C", "C sharp", "D", "D sharp", "E", "F", "F sharp", "G", "G sharp", "A", "A sharp", "B")
    return f"{names[note % 12]}{note // 12 - 1}"


@dataclass(frozen=True)
class ScoreNote:
    pitch: int
    duration: Fraction
    staff: str = "1"
    voice: str = "1"


@dataclass(frozen=True)
class ScoreEvent:
    """New attacks at one score position; times are in quarter-note beats."""

    onset: Fraction
    tones: tuple[ScoreNote, ...]
    measure: str = ""

    @property
    def pitches(self) -> tuple[int, ...]:
        return tuple(sorted({tone.pitch for tone in self.tones}))


@dataclass(frozen=True)
class ScoreRest:
    onset: Fraction
    duration: Fraction
    staff: str
    voice: str
    measure: str


@dataclass(frozen=True)
class Exercise:
    title: str
    notes: tuple[int, ...]
    events: tuple[ScoreEvent, ...] = ()
    rests: tuple[ScoreRest, ...] = ()
    duration: Fraction = Fraction(0)

    def __post_init__(self):
        if not self.events:
            object.__setattr__(self, "events", tuple(
                ScoreEvent(Fraction(i), (ScoreNote(n, Fraction(1)),))
                for i, n in enumerate(self.notes)))
        flattened = tuple(n for event in self.events for n in event.pitches)
        if flattened != self.notes:
            raise ValueError("Exercise notes must match its score events.")
        if any(type(n) is not int or not 0 <= n <= 127 for n in self.notes):
            raise ValueError("Notes must be MIDI integers from 0 to 127.")
        if any(not event.tones or event.onset < 0 or any(t.duration <= 0 for t in event.tones)
               for event in self.events):
            raise ValueError("Score events need pitches, nonnegative onsets and positive durations.")
        if any(a.onset >= b.onset for a, b in zip(self.events, self.events[1:])):
            raise ValueError("Score events must have strictly increasing onsets.")
        end = max((event.onset + t.duration for event in self.events for t in event.tones), default=Fraction(0))
        end = max(end, max((r.onset + r.duration for r in self.rests), default=Fraction(0)))
        object.__setattr__(self, "duration", max(self.duration, end))


def load_exercise(path: Path, *, part: str | None = None,
                  staff: str | None = None, voice: str | None = None,
                  start_measure: int | None = None, end_measure: int | None = None) -> Exercise:
    path = Path(path)
    if path.suffix.lower() in {".xml", ".musicxml", ".mxl"}:
        from .musicxml import load_musicxml
        return load_musicxml(path, part=part, staff=staff, voice=voice,
                             start_measure=start_measure, end_measure=end_measure)
    if path.suffix.lower() != ".json":
        raise ValueError("Use JSON, MusicXML (.musicxml/.xml), or compressed MusicXML (.mxl). PDF/image recognition is not supported.")
    if any(value is not None for value in (part, staff, voice, start_measure, end_measure)):
        raise ValueError("Part, staff, voice and measure selection apply only to MusicXML.")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Exercise must be a JSON object.")
    title, notes = data.get("title"), data.get("notes")
    if not isinstance(title, str) or not title.strip():
        raise ValueError("Exercise needs a nonempty title.")
    if not isinstance(notes, list) or not notes:
        raise ValueError("Exercise needs a nonempty notes list.")
    events = []
    for i, item in enumerate(notes):
        pitches = item if isinstance(item, list) else [item]
        if not pitches or any(type(n) is not int or not 0 <= n <= 127 for n in pitches):
            raise ValueError("Notes must be MIDI integers from 0 to 127, or nonempty chord lists.")
        if len(set(pitches)) != len(pitches):
            raise ValueError("A chord cannot contain duplicate pitches.")
        events.append(ScoreEvent(Fraction(i), tuple(ScoreNote(n, Fraction(1)) for n in sorted(pitches))))
    return Exercise(title, tuple(n for e in events for n in e.pitches), tuple(events))
