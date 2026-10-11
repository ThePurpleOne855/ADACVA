"""Desktop agent tests with injected models and voice, no cloud or speakers."""
from threading import Event
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch

import test_note_reader_gui as existing
from test_agent import FakeClient, Review, answer, call


class FakeVoice:
    available = True
    status = "Fake speech ready."
    def __init__(self):
        self.messages = []
        self.stopped = False
        self.closed = False
    def say(self, text):
        self.messages.append(text)
        done = Event()
        done.set()
        return done
    def stop(self):
        self.stopped = True
    def close(self):
        self.closed = True


@unittest.skipIf(existing.tk is None, "Tk unavailable")
class AgentGuiTests(unittest.TestCase):
    setUp = existing.NoteReaderGuiTests.setUp
    close_window = existing.NoteReaderGuiTests.close_window
    run_gui = existing.NoteReaderGuiTests.run_gui

    def prepare(self, client):
        panel = self.window.coach
        panel.voice.close()
        panel.voice = FakeVoice()
        panel.client = client
        self.window.score.loaded = Review()
        return panel

    def test_ask_fake_client_and_speak_toggle(self):
        panel = self.prepare(FakeClient([answer()]))
        panel.speak.set(True)
        panel.text.set("What should I practice?")
        panel.ask()
        self.run_gui(200)
        self.assertIn("measure six", panel.transcript.get("1.0", "end"))
        self.assertEqual(panel.voice.messages, ["Try measure six next."])
        panel.speak.set(False)
        panel._speech_changed()
        self.assertTrue(panel.voice.stopped)

    def test_responsive_model_request_and_stop_discards(self):
        started, release = Event(), Event()
        class Slow:
            def respond(self, *args):
                started.set()
                release.wait(2)
                return answer("Stale response")
        panel = self.prepare(Slow())
        panel.text.set("Give me a practice tip")
        panel.ask()
        self.assertTrue(started.wait(1))
        ticks = []
        self.root.after(5, lambda: ticks.append(True))
        self.run_gui(60)
        self.assertTrue(ticks)
        self.assertTrue(self.reader.connected)
        panel.stop()
        release.set()
        self.run_gui(100)
        self.assertNotIn("Stale response", panel.transcript.get("1.0", "end"))
        self.assertTrue(self.reader.connected)

    def test_api_failure_keeps_midi_score_and_local_practice(self):
        class Broken:
            def respond(self, *args):
                raise OSError("private error should not appear")
        panel = self.prepare(Broken())
        review = self.window.score.loaded
        panel.text.set("Give me a practice tip")
        panel.ask()
        self.run_gui(150)
        self.assertIn("unavailable", panel.transcript.get("1.0", "end"))
        self.assertTrue(self.reader.connected)
        self.assertIs(self.window.score.loaded, review)
        self.window.score.practice()
        self.assertIsNotNone(self.window.score.tutor)

    def test_no_score_and_changed_review(self):
        panel = self.prepare(FakeClient([]))
        review = self.window.score.loaded
        self.window.score.loaded = None
        panel.text.set("Give me a practice tip")
        panel.ask()
        self.assertIn("No piece is loaded", panel.transcript.get("1.0", "end"))
        result = panel._perform(review, "start_practice", {"start_measure": "6", "end_measure": "6"})
        self.assertEqual(result["status"], "rejected")

    def test_tool_dispatch_targets_local_practice(self):
        panel = self.prepare(FakeClient([call("start_practice", {"start_measure": "6", "end_measure": "6"}), answer()]))
        panel.text.set("Practice measure six")
        panel.ask()
        self.run_gui(200)
        self.assertEqual(self.window.score.tutor.exercise.notes, (65,))
        self.assertEqual(len(self.window.score.attempt.context["events"]), 1)

    def test_playback_announced_aloud_without_dialog(self):
        panel = self.prepare(FakeClient([]))
        panel.speak.set(True)
        spoken = Event()
        panel.voice.say = lambda text: spoken
        review = self.window.score.loaded
        args = {"start_measure": "6", "end_measure": "6", "tempo": 60}
        with patch("ada_piano.agent.gui.messagebox.askyesno") as dialog:
            self.assertEqual(panel._perform(review, "play_reference", args)["status"], "queued")
            dialog.assert_not_called()
        with patch.object(self.window.playback, "play_exercise") as play:
            panel._advance_actions()
            play.assert_not_called()
            spoken.set()
            panel._advance_actions()
            self.assertEqual(play.call_args.args[0].notes, (65,))

    def test_close_cleans_voice(self):
        panel = self.prepare(FakeClient([]))
        voice = panel.voice
        self.window.close()
        self.assertTrue(voice.closed)

    def test_local_stop_cancels_pending_announcement(self):
        panel = self.prepare(FakeClient([]))
        panel.speak.set(True)
        panel.voice.say = lambda text: Event()
        args = {"start_measure": "6", "end_measure": "6", "tempo": 60}
        panel._perform(self.window.score.loaded, "play_reference", args)
        self.window.score.stop()
        panel._advance_actions()
        self.assertIsNone(panel._pending_reference)

    def test_finished_reference_starts_target_only_after_your_turn(self):
        panel = self.prepare(FakeClient([]))
        review = self.window.score.loaded
        panel._activity_version = self.window.score.activity_version
        panel._reference_active = True
        panel._reference_review = review
        panel.speak.set(True)
        spoken = Event()
        panel.voice.say = lambda text: spoken
        self.window.playback.player = NS(status=NS(state="finished"), stop=lambda: None, close=lambda: None)
        panel._perform(review, "start_practice", {"start_measure": "6", "end_measure": "6"})
        panel._advance_actions()
        self.assertIsNone(self.window.score.tutor)
        spoken.set()
        panel._advance_actions()
        self.assertEqual(self.window.score.tutor.exercise.notes, (65,))
