import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

from ada_piano.ai_tutor import Tutor
from ada_piano.music_sheet import Exercise, load_exercise, note_name
from ada_piano.sound_sensor import event_from_message, simulated_notes


class TutorTests(unittest.TestCase):
    def test_wrong_note_does_not_advance_and_retry_completes(self):
        tutor = Tutor(Exercise("Two notes", (60, 62)))
        events = list(simulated_notes([59, 60, 63, 62, 64]))
        self.assertIn("higher", tutor.observe(events[0]))
        self.assertEqual(tutor.position, 0)
        self.assertIn("Play D4", tutor.observe(events[1]))
        self.assertIn("lower", tutor.observe(events[2]))
        self.assertEqual(tutor.position, 1)
        self.assertIn("Exercise complete", tutor.observe(events[3]))
        self.assertTrue(tutor.complete)
        self.assertIn("Exercise complete", tutor.observe(events[4]))
        self.assertEqual(tutor.position, 2)

    def test_midi_releases_and_other_messages_are_ignored(self):
        for message in [SimpleNamespace(type="note_off", note=60, velocity=90),
                        SimpleNamespace(type="note_on", note=60, velocity=0),
                        SimpleNamespace(type="clock")]:
            self.assertIsNone(event_from_message(message))
        event = event_from_message(SimpleNamespace(type="note_on", note=60, velocity=100))
        self.assertEqual((event.note, event.velocity, event.source), (60, 100, "midi"))

    def test_exercise_validation(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "exercise.json"
            for notes in ([], [128], [-1], [True], [60.5], ["C4"]):
                path.write_text(json.dumps({"title": "Test", "notes": notes}))
                with self.subTest(notes=notes), self.assertRaises(ValueError):
                    load_exercise(path)
            path.write_text(json.dumps({"title": "Test", "notes": [60, 62]}))
            self.assertEqual(load_exercise(path).notes, (60, 62))

    def test_middle_c(self):
        self.assertEqual(note_name(60), "C4")


if __name__ == "__main__":
    unittest.main()
