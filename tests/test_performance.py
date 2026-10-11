import unittest

from ada_piano import pieces
from ada_piano.ai_tutor.performance import PlayedNote, PlayThrough, compare, expected_notes


def perform(exercise, bpm=80, start=10.0, *, legato=0.9, change=None):
    """Simulate a faithful performance; change(note_index, note) may return None/edits."""
    spb = 60 / bpm
    played = []
    for index, note in enumerate(expected_notes(exercise)):
        onset = start + note.beat * spb
        item = PlayedNote(note.pitch, onset, onset + note.duration * spb * legato, 70)
        if change:
            item = change(index, note, item)
        if item is not None:
            played.extend(item if isinstance(item, list) else [item])
    return played


class PerformanceTests(unittest.TestCase):
    def setUp(self):
        self.ode = pieces.load(pieces.find("ode to joy")).exercise
        self.elise = pieces.load(pieces.find("fur elise"), "theme").exercise

    def test_clean_performance(self):
        report = compare(self.ode, perform(self.ode), target_bpm=80)
        self.assertEqual(report["pitch_accuracy_percent"], 100)
        self.assertTrue(report["complete"])
        self.assertEqual(report["tempo"]["estimated_bpm"], 80)
        self.assertEqual(report["measure_details"], [])
        self.assertEqual(len(report["clean_measures"]), 8)

    def test_wrong_missed_and_extra_do_not_shift_later_notes(self):
        def change(i, note, item):
            if i == 5:  # measure 2: F4 -> F sharp 4
                return PlayedNote(66, item.onset, item.release)
            if i == 9:  # measure 3: second C4 missed
                return None
            if i == 1:  # measure 1: extra G4 slipped in after the second E4
                return [item, PlayedNote(67, item.onset + 0.2, item.onset + 0.3)]
            return item
        report = compare(self.ode, perform(self.ode, change=change))
        details = {d["measure"]: d for d in report["measure_details"]}
        self.assertEqual(details["2"]["wrong"], [{"expected": "F4", "played": "F sharp4"}])
        self.assertEqual(details["3"]["missed"], ["C4"])
        self.assertEqual(details["1"]["extra"], ["G4"])
        self.assertEqual((report["wrong"], report["missed"], report["extra"]), (1, 1, 1))
        self.assertEqual(report["correct"], report["notes_expected"] - 2)
        self.assertNotIn("5", details)

    def test_stopping_early_is_not_reported_as_missed_notes(self):
        played = [n for n in perform(self.ode) if n.onset < 10 + 16 * 0.75]
        report = compare(self.ode, played)
        self.assertFalse(report["complete"])
        self.assertEqual(report["stopped_in_measure"], "4")
        self.assertEqual(report["missed"], 0)
        self.assertEqual(report["pitch_accuracy_percent"], 100)

    def test_steady_slow_tempo_is_not_late(self):
        report = compare(self.ode, perform(self.ode, bpm=50), target_bpm=80)
        self.assertEqual(report["tempo"]["estimated_bpm"], 50)
        self.assertEqual(report["late"] + report["early"], 0)

    def test_rushing_hesitation_and_short_notes(self):
        def change(i, note, item):
            if note.measure == "3":
                return PlayedNote(item.pitch, item.onset - 0.3, item.release - 0.3)
            if note.measure in {"5", "6", "7", "8"}:
                return PlayedNote(item.pitch, item.onset + 2, item.release + 2)
            if note.measure == "4" and note.duration == 2:
                return PlayedNote(item.pitch, item.onset, item.onset + 0.2)
            return item
        report = compare(self.ode, perform(self.ode, change=change))
        details = {d["measure"]: d for d in report["measure_details"]}
        self.assertEqual(len(details["3"]["early"]), 4)
        self.assertEqual(details["5"]["hesitations"], 1)
        self.assertEqual(details["4"]["short"], ["D4"])
        self.assertIn("3", report["measures_needing_work"])

    def test_two_hand_chords_tolerate_attack_order(self):
        def change(i, note, item):  # right hand slightly before the left in chords
            return PlayedNote(item.pitch, item.onset + (0.02 if note.pitch < 60 else 0), item.release)
        report = compare(self.elise, perform(self.elise, bpm=60, change=change))
        self.assertEqual(report["pitch_accuracy_percent"], 100)
        self.assertEqual(report["notes_expected"], 55)  # 49 attacks, 6 of them two-note chords

    def test_fast_detached_notes_keep_their_order(self):
        played = []
        for i, pitch in enumerate([64, 64, 65, 67, 67, 65, 64, 62]):  # 30 ms apart, never held together
            played.append(PlayedNote(pitch, 1 + i * 0.03, 1 + i * 0.03 + 0.02))
        report = compare(self.ode, played)
        self.assertEqual((report["correct"], report["wrong"]), (8, 0))

    def test_play_through_pairs_presses_and_releases(self):
        take = PlayThrough(1.0)
        take.observe("on", 60, 80, 1, 0.5)  # before start: ignored
        take.observe("on", 60, 80, 1, 1.1)
        take.observe("on", 64, 80, 1, 1.2)
        take.observe("off", 60, 0, 1, 1.6)
        self.assertTrue(take.held)
        self.assertEqual(take.idle_for(9), 0)
        take.observe("off", 64, 0, 1, 1.7)
        self.assertAlmostEqual(take.idle_for(3.7), 2.0)
        take.finish(4)
        take.observe("on", 65, 80, 1, 5)
        self.assertEqual([(n.pitch, n.onset, n.release) for n in take.notes], [(60, 1.1, 1.6), (64, 1.2, 1.7)])


if __name__ == "__main__":
    unittest.main()
