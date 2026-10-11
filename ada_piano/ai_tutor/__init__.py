"""Deterministic first tutor; a future language model can explain its results."""

from ada_piano.music_sheet import Exercise, note_name
from ada_piano.sound_sensor import NoteEvent
from math import isfinite
from .results import TutorResult


class Tutor:
    def __init__(self, exercise: Exercise, chord_window: float = 0.15):
        if not exercise.notes:
            raise ValueError("Exercise needs at least one note.")
        self.exercise = exercise
        self.position = 0
        if not isfinite(chord_window) or chord_window <= 0:
            raise ValueError("Chord window must be a positive, finite number of seconds.")
        self.chord_window = chord_window
        self.held = set()
        self.attacks = {}
        self.chord_mode = any(len(e.pitches) > 1 for e in exercise.events)

    @property
    def complete(self) -> bool:
        return self.position == len(self.exercise.events)

    def prompt(self) -> str:
        if self.complete:
            return "Exercise complete. Well done."
        pitches = self.exercise.events[self.position].pitches
        names = " + ".join(note_name(n) for n in pitches)
        return f"Play {names}{' together' if len(pitches) > 1 else ''}."

    def observe(self, event: NoteEvent) -> str | None:
        result = self.evaluate(event)
        return result.message if result is not None else None

    def _result(self, kind, message, played=(), spread=None):
        index = self._event_index
        current = self.exercise.events[index]
        return TutorResult(kind, self._timestamp, index, current.measure,
                           current.pitches, tuple(note_name(n) for n in current.pitches),
                           tuple(played), tuple(note_name(n) for n in played), message,
                           self.complete, spread,
                           self.chord_window * 1000 if spread is not None else None)

    def evaluate(self, event: NoteEvent) -> TutorResult | None:
        """Evaluate once; observe() renders the same result for legacy callers."""
        if not isfinite(event.timestamp):
            raise ValueError("MIDI timestamp must be finite.")
        self._timestamp = event.timestamp
        self._event_index = min(self.position, len(self.exercise.events) - 1)
        if self.complete:
            return self._result("exercise_complete", self.prompt())
        key = (event.channel, event.note)
        if event.kind == "note_off" or event.velocity == 0:
            self.held.discard(key)
            if not any(pitch == event.note for _, pitch in self.held):
                self.attacks.pop(event.note, None)
            return self._try_advance()
        if event.kind != "note_on":
            return None
        already_held = key in self.held
        self.held.add(key)
        current = self.exercise.events[self.position]
        expected = set(current.pitches)
        if event.note not in expected:
            if len(expected) == 1:
                direction = "higher" if event.note < next(iter(expected)) else "lower"
                return self._result("wrong_note", f"You played {note_name(event.note)}. Try {direction}. {self.prompt()}", (event.note,))
            return self._result("unexpected_note", f"Unexpected {note_name(event.note)}. Release it. {self.prompt()}", (event.note,))
        # Old note-on-only callers retain single-note behavior; chord exercises
        # require releases before retriggering pitches in subsequent attacks.
        if already_held and self.chord_mode:
            return self._result("replay_required", f"Release and replay {note_name(event.note)}. {self.prompt()}", (event.note,))
        self.attacks[event.note] = event.timestamp
        return self._try_advance()

    def _try_advance(self) -> TutorResult | None:
        if not self.attacks:
            return None
        current = self.exercise.events[self.position]
        expected = set(current.pitches)
        if self.chord_mode:
            sustained = {tone.pitch for earlier in self.exercise.events[:self.position]
                         for tone in earlier.tones
                         if earlier.onset + tone.duration > current.onset}
            extra = {pitch for _, pitch in self.held} - expected - sustained
            if extra:
                return self._result("extra_key", "Release " + ", ".join(note_name(n) for n in sorted(extra)) + f". {self.prompt()}", sorted(extra))
        if not expected <= self.attacks.keys():
            return None
        times = [self.attacks[n] for n in expected]
        spread = (max(times) - min(times)) * 1000
        if spread > self.chord_window * 1000:
            self.attacks.clear()
            return self._result("chord_attack_spread", f"Play the chord closer together. Release and retry. {self.prompt()}", sorted(expected), spread)
        self.position += 1
        self.attacks.clear()
        return self._result("correct", f"Correct. {self.prompt()}", sorted(expected), spread if len(expected) > 1 else None)
