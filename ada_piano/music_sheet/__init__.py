"""Structured exercises; score image recognition is outside the first prototype."""

from dataclasses import dataclass
import json
from pathlib import Path


def note_name(note: int) -> str:
    names = ("C", "C sharp", "D", "D sharp", "E", "F", "F sharp", "G", "G sharp", "A", "A sharp", "B")
    return f"{names[note % 12]}{note // 12 - 1}"


@dataclass(frozen=True)
class Exercise:
    title: str
    notes: tuple[int, ...]


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
    if any(type(n) is not int or not 0 <= n <= 127 for n in notes):
        raise ValueError("Notes must be MIDI integers from 0 to 127.")
    return Exercise(title, tuple(notes))
