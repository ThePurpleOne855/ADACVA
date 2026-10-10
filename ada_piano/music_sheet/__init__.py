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


def load_exercise(path: Path) -> Exercise:
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
