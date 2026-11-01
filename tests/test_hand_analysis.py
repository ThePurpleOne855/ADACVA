"""Calibrated MIDI/camera evidence without camera hardware or vision packages."""

import json
import unittest

from ada_piano.camera.analysis import HandAnalysis, MAX_ATTACKS, describe
from ada_piano.camera.stream import CameraFrame, HandLandmark


def key_position(pitch):
    white = (0, 2, 4, 5, 7, 9, 11)
    octave, chroma = divmod(pitch, 12)
    key = white.index(chroma) if chroma in white else sum(c < chroma for c in white) - 0.5
    return 0.25 + (octave * 7 + key - 35) * 0.035, 0.5 if chroma in white else 0.42


def hand(pitch, finger=8, extra=(), offset=(0, 0)):
    points = [HandLandmark(0.95, 0.95, 0)] * 21
    x, y = key_position(pitch)
    points[finger] = HandLandmark(x + offset[0], y + offset[1], 0)
    for index, other_pitch in extra:
        points[index] = HandLandmark(*key_position(other_pitch), 0)
    return tuple(points)


def frame(timestamp, hands=(), labels=()):
    return CameraFrame(b"", len(hands), captured_at_ns=round(timestamp * 1_000_000_000),
                       hand_landmarks=tuple(hands), handedness=tuple(labels))


def camera_samples(analyzer, timestamp, hands, labels=("right",)):
    for delta in (-0.04, 0.04):
        analyzer.add_frame(frame(timestamp + delta, hands, labels))


def calibration_press(analyzer, pitch, timestamp, *, labels=("right",), offset=(0, 0)):
    camera_samples(analyzer, timestamp, [hand(pitch, offset=offset)], labels)
    analyzer.observe("on", pitch, 90, 1, timestamp)
    messages = analyzer.tick(timestamp + 0.2)
    analyzer.observe("off", pitch, 0, 1, timestamp + 0.5)
    return messages


def calibrated(black=True, label="right", actual="right"):
    analyzer = HandAnalysis()
    analyzer.begin_calibration(actual)
    for pitch, timestamp in [(60, 10), (67, 11), (72, 12)]:
        calibration_press(analyzer, pitch, timestamp, labels=(label,))
    if black:
        calibration_press(analyzer, 61, 13, labels=(label,))
        calibration_press(analyzer, 70, 14, labels=(label,))
    else:
        analyzer.finish_calibration()
    return analyzer


class CalibrationTests(unittest.TestCase):
    def test_unknown_hand_label_cannot_establish_calibration(self):
        analyzer = HandAnalysis()
        analyzer.begin_calibration()
        for pitch, timestamp in [(60, 10), (67, 11), (72, 12)]:
            self.assertIn("cannot identify", calibration_press(analyzer, pitch, timestamp, labels=(None,))[0])
        self.assertFalse(analyzer.calibrated)

    def test_spoken_white_and_black_calibration_and_bounded_ranges(self):
        analyzer = HandAnalysis()
        self.assertIn("left", analyzer.begin_calibration("left"))
        first = calibration_press(analyzer, 60, 10, labels=("left",))
        self.assertIn("C4", first[0])
        self.assertFalse(analyzer.calibrated)
        self.assertIn("three", analyzer.finish_calibration())
        calibration_press(analyzer, 67, 11, labels=("left",))
        white = calibration_press(analyzer, 72, 12, labels=("left",))
        self.assertTrue(analyzer.calibrated)
        self.assertTrue(analyzer.calibrating)
        self.assertIn("black keys", white[0])
        calibration_press(analyzer, 61, 13, labels=("left",))
        complete = calibration_press(analyzer, 70, 14, labels=("left",))
        self.assertFalse(analyzer.calibrating)
        self.assertIn("calibration complete", complete[0])
        rows = analyzer.summary()["calibration"]["rows"]
        self.assertEqual((rows["white"]["first_midi"], rows["white"]["last_midi"]), (60, 72))
        self.assertEqual((rows["black"]["first_midi"], rows["black"]["last_midi"]), (61, 70))

    def test_duplicate_close_and_narrow_anchors_do_not_complete(self):
        analyzer = HandAnalysis()
        analyzer.begin_calibration()
        calibration_press(analyzer, 60, 10)
        self.assertIn("already captured", calibration_press(analyzer, 60, 11)[0])
        self.assertIn("farther", calibration_press(analyzer, 62, 12)[0])
        calibration_press(analyzer, 64, 13)
        calibration_press(analyzer, 67, 14)
        self.assertFalse(analyzer.calibrated)

    def test_black_keys_need_white_axis_first_and_separated_black_anchors(self):
        analyzer = HandAnalysis()
        analyzer.begin_calibration()
        self.assertIn("Start with", calibration_press(analyzer, 61, 10)[0])
        analyzer = calibrated(False)
        analyzer.calibrating = True
        calibration_press(analyzer, 61, 15)
        calibration_press(analyzer, 66, 16)
        self.assertNotIn("black", analyzer.summary()["calibration"]["rows"])
        self.assertTrue(analyzer.calibrating)

    def test_non_linear_or_stationary_geometry_is_rejected(self):
        for offset in [(0, 0.12), (-0.245, 0)]:
            with self.subTest(offset=offset):
                analyzer = HandAnalysis()
                analyzer.begin_calibration()
                calibration_press(analyzer, 60, 10)
                calibration_press(analyzer, 67, 11)
                result = calibration_press(analyzer, 72, 12, offset=offset)
                self.assertIn("does not fit", result[0])
                self.assertFalse(analyzer.calibrated)

    def test_black_row_with_different_camera_scale_is_rejected(self):
        analyzer = calibrated(False)
        analyzer.calibrating = True
        calibration_press(analyzer, 61, 15)
        result = calibration_press(analyzer, 70, 16, offset=(0.1, 0))
        self.assertIn("does not fit", result[0])
        self.assertNotIn("black", analyzer.summary()["calibration"]["rows"])

    def test_calibration_requires_one_visible_hand_and_stable_identity(self):
        analyzer = HandAnalysis()
        analyzer.begin_calibration()
        camera_samples(analyzer, 10, [hand(60), hand(72)], ("right", "left"))
        analyzer.observe("on", 60, 80, 1, 10)
        self.assertIn("only your right hand", analyzer.tick(10.2)[0])
        analyzer.observe("off", 60, 0, 1, 10.5)
        calibration_press(analyzer, 60, 11)
        result = calibration_press(analyzer, 67, 12, labels=("left",))
        self.assertIn("Hand identity changed", result[0])

    def test_moving_finger_and_chords_are_not_calibration_anchors(self):
        analyzer = HandAnalysis()
        analyzer.begin_calibration()
        analyzer.add_frame(frame(9.96, [hand(60)], ["right"]))
        analyzer.add_frame(frame(10.04, [hand(60, offset=(0.03, 0))], ["right"]))
        analyzer.observe("on", 60, 80, 1, 10)
        self.assertIn("moved", analyzer.tick(10.2)[0])
        analyzer.observe("off", 60, 0, 1, 10.5)
        camera_samples(analyzer, 11, [hand(60)])
        analyzer.observe("on", 60, 80, 1, 11)
        analyzer.observe("on", 64, 80, 1, 11.01)
        self.assertTrue(all("one calibration key" in message for message in analyzer.tick(11.3)))
        self.assertFalse(analyzer.calibrated)

    def test_white_only_finish_and_cancel_are_explicit(self):
        analyzer = calibrated(False)
        self.assertIn("Black key observations will be unknown", analyzer.finish_calibration())
        self.assertIn("cancelled", analyzer.cancel_calibration())
        self.assertFalse(analyzer.calibrated)
        self.assertFalse(analyzer.calibrating)


class AssociationTests(unittest.TestCase):
    def attack(self, analyzer, pitch, timestamp=20, *, hands=None, labels=("right",)):
        if hands is not None:
            camera_samples(analyzer, timestamp, hands, labels)
        analyzer.observe("on", pitch, 80, 1, timestamp)
        analyzer.tick(timestamp + 0.2)
        analyzer.observe("off", pitch, 0, 1, timestamp + 0.5)

    def test_association_waits_for_camera_and_contains_only_bounded_evidence(self):
        analyzer = calibrated()
        analyzer.begin_take(19)
        analyzer.add_frame(frame(19.96, [hand(64, finger=12)], ["right"]))
        analyzer.observe("on", 64, 80, 1, 20)
        analyzer.tick(20.1)
        self.assertEqual(analyzer.summary()["pending"], 1)
        analyzer.add_frame(frame(20.04, [hand(64, finger=12)], ["right"]))
        analyzer.tick(20.2)
        result = analyzer.finish_take(21)
        self.assertEqual(result["associated"], 1)
        self.assertEqual(result["unknown"], 0)
        self.assertEqual(result["coverage_percent"], 100)
        self.assertEqual(result["observations"][0]["finger"], 3)
        self.assertEqual(result["observations"][0]["hand"], "right")
        self.assertEqual(result["observations"][0]["note"], "E4")
        self.assertEqual(result["observations"][0]["time_seconds"], 1)
        self.assertNotIn("landmarks", json.dumps(result))
        self.assertIn("do not judge", describe(result))

    def test_mirrored_handedness_is_resolved_by_anatomical_calibration_hand(self):
        analyzer = calibrated(label="left", actual="right")
        analyzer.begin_take(19)
        self.attack(analyzer, 64, hands=[hand(64)], labels=("left",))
        self.attack(analyzer, 67, 21, hands=[hand(67)], labels=("right",))
        hands = [o["hand"] for o in analyzer.summary()["observations"]]
        self.assertEqual(hands, ["right", "left"])

    def test_black_key_uses_separate_contact_line(self):
        analyzer = calibrated()
        analyzer.begin_take(19)
        self.attack(analyzer, 66, hands=[hand(66)])
        self.assertEqual(analyzer.summary()["associated"], 1)
        self.attack(analyzer, 66, 21, hands=[hand(66, offset=(0, 0.08))])
        self.assertEqual(analyzer.summary()["unknown_reasons"], {"no_finger_near_key": 1})

    def test_uncalibrated_black_and_off_range_notes_abstain(self):
        analyzer = calibrated(False)
        analyzer.begin_take(19)
        self.attack(analyzer, 61, hands=[hand(61)])
        self.attack(analyzer, 74, 21, hands=[hand(74)])
        self.assertEqual(analyzer.summary()["unknown_reasons"],
                         {"black_keys_uncalibrated": 1, "outside_calibrated_range": 1})

    def test_distinct_chord_fingers_associate_but_ambiguous_fingers_do_not(self):
        analyzer = calibrated()
        analyzer.begin_take(19)
        camera_samples(analyzer, 20, [hand(60, extra=((12, 64),))])
        analyzer.observe("on", 60, 80, 1, 20)
        analyzer.observe("on", 64, 80, 1, 20.01)
        analyzer.tick(20.25)
        self.assertEqual(analyzer.summary()["associated"], 2)
        self.attack(analyzer, 67, 21, hands=[hand(67, extra=((12, 67),))])
        self.assertEqual(analyzer.summary()["unknown_reasons"], {"ambiguous_fingers": 1})

    def test_duplicate_or_missing_handedness_abstains(self):
        analyzer = calibrated()
        analyzer.begin_take(19)
        self.attack(analyzer, 64, hands=[hand(64), hand(67)], labels=("right", "right"))
        self.attack(analyzer, 64, 21, hands=[hand(64)], labels=())
        self.assertEqual(analyzer.summary()["unknown_reasons"], {"ambiguous_handedness": 2})

    def test_no_camera_no_hands_and_incomplete_frames_abstain(self):
        analyzer = calibrated()
        analyzer.begin_take(19)
        self.attack(analyzer, 64)
        self.attack(analyzer, 64, 21, hands=[])
        analyzer.add_frame(frame(22.03, [hand(64)], ["right"]))
        analyzer.observe("on", 64, 80, 1, 22)
        analyzer.tick(22.2)
        self.assertEqual(analyzer.summary()["unknown_reasons"],
                         {"stale_or_missing_camera": 1, "no_hands": 1, "insufficient_frames": 1})

    def test_invalid_landmarks_abstain_and_out_of_order_frames_are_ignored(self):
        analyzer = calibrated()
        analyzer.begin_take(19)
        points = list(hand(64))
        points[8] = HandLandmark(float("nan"), 0.5, 0)
        camera_samples(analyzer, 20, [points])
        analyzer.add_frame(frame(19, [hand(64)], ["right"]))
        self.attack(analyzer, 64)
        self.assertEqual(analyzer.summary()["unknown_reasons"], {"invalid_landmarks": 1})

    def test_unstable_identity_and_camera_motion_abstain(self):
        for second, reason in [(hand(64, finger=12), "unstable_finger_identity"),
                               (hand(64, offset=(0.006, 0.006)), "moving_finger")]:
            with self.subTest(reason=reason):
                analyzer = calibrated()
                analyzer.begin_take(19)
                offset = (-0.006, -0.006) if reason == "moving_finger" else (0, 0)
                analyzer.add_frame(frame(19.96, [hand(64, offset=offset)], ["right"]))
                analyzer.add_frame(frame(20.04, [second], ["right"]))
                self.attack(analyzer, 64)
                self.assertEqual(analyzer.summary()["unknown_reasons"], {reason: 1})

    def test_reset_preserves_take_and_rejects_future_uncalibrated_attacks(self):
        analyzer = calibrated()
        analyzer.begin_take(19)
        self.attack(analyzer, 64, hands=[hand(64)])
        analyzer.observe("on", 67, 80, 1, 21)
        analyzer.reset("Camera source changed.")
        self.attack(analyzer, 69, 22, hands=[hand(69)])
        result = analyzer.finish_take(23)
        self.assertEqual(result["associated"], 1)
        self.assertEqual(result["midi_attacks"], 3)
        self.assertEqual(result["unknown_reasons"], {"calibration_reset": 1, "uncalibrated": 1})
        self.assertFalse(result["calibrated"])
        self.assertEqual(result["calibration_invalidations"], ["Camera source changed."])

    def test_new_take_has_no_previous_observations_and_summary_is_a_snapshot(self):
        analyzer = calibrated()
        analyzer.begin_take(19)
        self.attack(analyzer, 64, hands=[hand(64)])
        first = analyzer.finish_take(21)
        first["observations"][0]["hand"] = "modified"
        self.assertEqual(analyzer.summary()["observations"][0]["hand"], "right")
        analyzer.begin_take(22)
        self.assertEqual(analyzer.summary()["midi_attacks"], 0)
        self.assertEqual(analyzer.summary()["observations"], [])
        self.assertTrue(analyzer.calibrated)
        self.assertEqual(analyzer.summary()["unknown_reasons"], {})

    def test_notes_without_calibration_are_explicitly_unknown_and_bounded(self):
        analyzer = HandAnalysis()
        analyzer.begin_take(0)
        for index in range(MAX_ATTACKS + 2):
            analyzer.observe("on", 60, 80, 1, index / 100)
        analyzer.finish_take(20)
        result = analyzer.summary()
        self.assertEqual(result["midi_attacks"], MAX_ATTACKS)
        self.assertEqual(result["ignored_attacks"], 2)
        self.assertEqual(result["unknown"], MAX_ATTACKS)
        self.assertEqual(result["unknown_reasons"], {"uncalibrated": MAX_ATTACKS})
        self.assertLess(len(json.dumps(result)), 2000)

    def test_invalid_inputs_and_nonmonotonic_midi_are_rejected(self):
        analyzer = HandAnalysis()
        for event in [("bad", 60, 80, 1, 1), ("on", 128, 80, 1, 1), ("on", 60, 128, 1, 1),
                      ("on", 60, 80, 0, 1), ("on", 60, 80, 1, float("nan")),
                      ("on", True, 80, 1, 1)]:
            with self.subTest(event=event), self.assertRaises(ValueError):
                analyzer.observe(*event)
        with self.assertRaises(ValueError):
            analyzer.begin_calibration("both")
        with self.assertRaises(ValueError):
            analyzer.begin_take(-1)
        with self.assertRaises(ValueError):
            analyzer.tick(float("inf"))
        analyzer.observe("off", 60, 0, 1, 2)
        with self.assertRaises(ValueError):
            analyzer.observe("on", 60, 80, 1, 1)


if __name__ == "__main__":
    unittest.main()
