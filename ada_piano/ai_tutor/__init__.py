"""Deterministic first tutor; a future language model can explain its results."""

from ada_piano.music_sheet import Exercise, note_name
from ada_piano.sound_sensor import NoteEvent


class Tutor:
    def __init__(self, exercise: Exercise):
        if not exercise.notes:
            raise ValueError("Exercise needs at least one note.")
        self.exercise = exercise
        self.position = 0

    @property
    def complete(self) -> bool:
        return self.position == len(self.exercise.notes)

    def prompt(self) -> str:
        if self.complete:
            return "Exercise complete. Well done."
        return f"Play {note_name(self.exercise.notes[self.position])}."

    def observe(self, event: NoteEvent) -> str:
        if self.complete:
            return self.prompt()
        expected = self.exercise.notes[self.position]
        if event.note != expected:
            direction = "higher" if event.note < expected else "lower"
            return f"You played {note_name(event.note)}. Try {direction}. {self.prompt()}"
        self.position += 1
        return f"Correct. {self.prompt()}"
