"""Live demo feedback uses measured MIDI and the guided tutor's score order."""

import unittest

from ada_piano.music_sheet import Exercise
from ada_piano.note_reader import NoteEvent
from ada_piano.note_reader.practice import LivePractice
from test_chords import exercise


def press(note, timestamp=1, kind="on", channel=1):
    return NoteEvent(kind, note, 80 if kind == "on" else 0, channel, timestamp)


class LivePracticeTests(unittest.TestCase):
    def setUp(self):
        self.live = LivePractice()
        self.score = Exercise("Two notes", (60, 62))
        self.live.sync(self.score, 1)

    def test_wrong_note_waits_and_correct_note_keeps_its_color_after_advance(self):
        self.live.observe(press(61), "Piano")
        self.assertEqual(self.live.expected, (60,))
        self.assertEqual(self.live.feedback([(1, 61)]), {61: False})
        self.live.observe(press(61, kind="off"), "Piano")
        self.live.observe(press(60), "Piano")
        self.assertEqual(self.live.expected, (62,))
        self.assertEqual(self.live.feedback([(1, 60)]), {60: True})
        self.live.observe(press(60, kind="off"), "Piano")
        self.assertEqual(self.live.verdicts, {})
        self.live.observe(press(62), "Piano")
        self.assertEqual(self.live.expected, ())
        self.assertTrue(self.live.tutor.complete)

    def test_reference_and_simulated_input_do_not_grade_or_advance(self):
        for source in ("Reference", "Demo"):
            self.live.observe(press(60), source)
            self.assertEqual(self.live.expected, (60,))
            self.assertEqual(self.live.feedback([(1, 60)]), {60: None})

    def test_passage_and_attempt_changes_clear_feedback_but_polling_does_not(self):
        self.live.observe(press(60), "Piano")
        self.live.sync(self.score, 1)
        self.assertEqual(self.live.expected, (62,))
        self.live.sync(self.score, 2)
        self.assertEqual(self.live.expected, (60,))
        self.assertEqual(self.live.verdicts, {})
        self.live.sync(Exercise("New passage", (65,)), 2)
        self.assertEqual(self.live.expected, (65,))
        self.live.sync(None, 3)
        self.assertEqual(self.live.expected, ())
        self.live.observe(press(60), "Piano")
        self.assertEqual(self.live.feedback([(1, 60)]), {60: None})

    def test_chord_waits_for_all_notes_and_flags_slow_attack(self):
        self.live.sync(exercise((60, 64, 67), (62, 65, 69)), 1)
        self.live.observe(press(60, 1), "Piano")
        self.live.observe(press(64, 1.02), "Piano")
        self.assertEqual(self.live.tutor.position, 0)
        self.live.observe(press(67, 1.04), "Piano")
        self.assertEqual(self.live.tutor.position, 1)
        for note in (60, 64, 67):
            self.live.observe(press(note, 1.1, "off"), "Piano")
        self.live.observe(press(62, 2), "Piano")
        self.live.observe(press(65, 2.5), "Piano")
        self.live.observe(press(69, 2.6), "Piano")
        self.assertEqual(self.live.tutor.position, 1)
        self.assertEqual(self.live.feedback([(1, 62), (1, 65), (1, 69)]), {62: False, 65: False, 69: False})

    def test_complete_passage_can_restart(self):
        for pitch in self.score.notes:
            self.live.observe(press(pitch), "Piano")
        self.live.restart()
        self.assertEqual(self.live.expected, (60,))
        self.assertEqual(self.live.verdicts, {})
