"""Agent-only regression tests; no Tk display, MIDI, speech or network needed.

Run: python -m unittest ada_piano.agent.test_reliability -v
"""
from queue import Queue
from threading import Event
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock, patch

from .gui import CoachPanel


class ReliabilityTests(unittest.TestCase):
    def panel(self):
        panel = CoachPanel.__new__(CoachPanel)
        review = NS(approved=True, digest="score")
        playback = NS(player=NS(status=NS(state="idle")), tempo=Mock(),
                      play_exercise=Mock(), status=Mock())
        panel.score = NS(loaded=review, activity_version=1, playback=playback,
                         tutor=None, latest_attempt=None, stop=Mock(), practice=Mock())
        panel._request_review = review
        panel._request_attempt = None
        panel._request_playback_status = playback.player.status
        panel._activity_version = 1
        panel._reference_outcome = None
        panel._reference_waiter = None
        panel._pending_reference = panel._pending_practice = None
        panel._reference_active = False
        panel._reference_review = None
        panel._turn_ready = None
        panel._cancel = Event()
        panel.voice = Mock()
        panel.voice.status = "Fake voice ready."
        panel.status = Mock()
        panel.speak = Mock()
        panel.speak.get.return_value = False
        panel._append = Mock()
        panel._queue = Queue()
        panel._thread = None
        panel.ask_button = Mock()
        panel._closed = True
        return panel

    def test_late_action_cannot_replace_new_practice(self):
        panel = self.panel()
        new_tutor = panel.score.tutor = object()
        panel.score.activity_version += 1
        result = panel._perform(panel.score.loaded, "start_practice", {})
        self.assertEqual(result["status"], "cancelled")
        self.assertIs(panel.score.tutor, new_tutor)
        panel.score.stop.assert_not_called()
        panel.score.practice.assert_not_called()

    def test_local_stop_discards_late_answer(self):
        panel = self.panel()
        panel._queue.put(("answer", panel._cancel, (panel.score.loaded, "stale", [])))
        panel.score.activity_version += 1
        panel._poll()
        panel._append.assert_not_called()
        self.assertTrue(panel._cancel.is_set())

    def test_feedback_attaches_to_request_attempt_not_new_latest(self):
        panel = self.panel()
        original = panel._request_attempt = NS(context={"sha256": "score"}, feedback=[])
        newer = panel.score.latest_attempt = NS(context={"sha256": "score"}, feedback=[])
        panel._queue.put(("answer", panel._cancel, (panel.score.loaded, "feedback", [])))
        panel._poll()
        self.assertEqual(original.feedback, ["feedback"])
        self.assertEqual(newer.feedback, [])

    def test_reference_waiter_resolves_only_on_terminal_outcome(self):
        panel = self.panel()
        done, box = Event(), {}
        panel._queue.put(("action", panel._cancel,
                          (panel.score.loaded, "play_reference", {}, done, box)))
        with patch.object(panel, "_perform", return_value={"status": "queued"}):
            panel._poll()
        self.assertFalse(done.is_set())
        panel._finish_reference("failed")
        self.assertTrue(done.is_set())
        self.assertEqual(box["result"], {"status": "failed"})

    def test_failed_reference_blocks_late_practice(self):
        panel = self.panel()
        panel._finish_reference("failed")
        with patch("ada_piano.agent.gui.select_passage", return_value=object()):
            result = panel._perform(panel.score.loaded, "start_practice",
                                    {"start_measure": "1", "end_measure": "1"})
        self.assertEqual(result["status"], "rejected")
        panel.score.practice.assert_not_called()

    def test_cancel_releases_waiter_without_stopping_local_work(self):
        panel = self.panel()
        done, box = Event(), {}
        panel._reference_waiter = (done, box)
        panel._cancel_request()
        self.assertTrue(done.is_set())
        self.assertEqual(box["result"]["status"], "cancelled")
        panel.score.stop.assert_not_called()

    def test_manual_playback_invalidates_request(self):
        panel = self.panel()
        panel.score.playback.player.status = NS(state="playing")
        self.assertTrue(panel._request_stale())

    def test_successful_reference_returns_completed(self):
        panel = self.panel()
        done, box = Event(), {}
        panel._reference_waiter = (done, box)
        panel._reference_active = True
        panel._reference_review = panel.score.loaded
        panel.score.playback.player.status = NS(state="finished")
        panel._advance_actions()
        self.assertEqual(box["result"], {"status": "completed"})
        self.assertTrue(done.is_set())

    def test_reference_start_failure_resolves_waiter(self):
        panel = self.panel()
        done, box, spoken = Event(), {}, Event()
        spoken.set()
        panel._reference_waiter = (done, box)
        panel._pending_reference = (panel.score.loaded, object(), 90, spoken)
        panel._advance_actions()
        self.assertTrue(done.is_set())
        self.assertEqual(box["result"]["status"], "failed")

    def test_own_practice_updates_expected_activity_version(self):
        panel = self.panel()
        panel.score.feedback = Mock()
        def practice(*args):
            panel.score.activity_version += 2
            panel.score.tutor = object()
        panel.score.practice.side_effect = practice
        with patch("ada_piano.agent.gui.select_passage", return_value=NS(events=[])), \
                patch("ada_piano.agent.gui.passage_context",
                      return_value={"selection": {}, "events": [], "rests": []}):
            result = panel._perform(panel.score.loaded, "start_practice",
                                    {"start_measure": "1", "end_measure": "1"})
        self.assertEqual(result["status"], "practicing")
        self.assertFalse(panel._request_stale())

    def test_selection_change_cancels_waiter(self):
        panel = self.panel()
        done, box = Event(), {}
        panel._reference_waiter = (done, box)
        panel.score.loaded = None
        panel._poll()
        self.assertTrue(done.is_set())
        self.assertEqual(box["result"]["status"], "cancelled")
        panel.score.stop.assert_not_called()


if __name__ == "__main__":
    unittest.main()
