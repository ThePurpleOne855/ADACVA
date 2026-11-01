"""Main voice surface, calibrated MIDI evidence and local saves with fake devices."""

import gc
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from time import monotonic
import unittest
from unittest.mock import patch

import test_note_reader_gui as existing
from test_agent_gui import FakeVoice
from test_agent import FakeClient, answer
from test_hand_analysis import calibration_press, camera_samples, hand
from test_note_reader import FakeBackend, note
from test_playback import FakeOutputBackend, message

from ada_piano.agent.test_input import FakeMicrophone
from ada_piano.note_reader import NoteEvent, NoteReader
from ada_piano.playback import ReferencePlayer


@unittest.skipIf(existing.tk is None, "Tk unavailable")
class AccessibleIntegrationTests(unittest.TestCase):
    run_gui = existing.NoteReaderGuiTests.run_gui

    def setUp(self):
        try:
            self.root = existing.tk.Tk()
        except existing.tk.TclError as exc:
            self.skipTest(str(exc))
        self.root.withdraw()
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.backend = FakeBackend()
        self.voice, self.microphone = FakeVoice(), FakeMicrophone()
        with patch("ada_piano.camera.gui.best_camera", return_value=(0, "Camera 0")), \
                patch("ada_piano.agent.gui.CoachPanel.use_best_voice"):
            self.window = existing.NoteReaderWindow(self.root, reader=NoteReader(self.backend),
                player=ReferencePlayer(FakeOutputBackend(), message_factory=message),
                camera_worker=existing.FakeCameraWorker(), voice=self.voice, microphone=self.microphone,
                accessible=True, session_directory=self.temp.name)
        self.window.keyboard._draw()
        self.addCleanup(self.close_window)

    def close_window(self):
        self.window.close()
        self.window = None
        gc.collect()

    def say(self, words):
        self.window.submit(words)

    def test_minimal_view_submit_transcript_and_tools_return(self):
        w = self.window
        self.assertEqual(w.workspace.winfo_manager(), "")
        self.assertEqual(w.home.winfo_manager(), "pack")
        w.home.entry.insert(0, "practice ode to joy")
        w.home._send()
        self.assertEqual(w.score.loaded.piece["id"], "ode_to_joy")
        self.assertIn("Loaded Ode to Joy", w.home.transcript.get("1.0", "end"))
        self.say("show tools")
        self.assertEqual(w.workspace.winfo_manager(), "pack")
        self.say("hide tools")
        self.assertEqual(w.home.winfo_manager(), "pack")
        self.assertEqual(w.home.entry.get(), "")

    def test_voice_selects_devices_tempo_and_approved_measures(self):
        self.say("list MIDI inputs")
        self.assertIn("1: USB MIDI", self.voice.messages[-1])
        self.say("select MIDI input one")
        self.assertTrue(self.window.reader.connected)
        self.say("practice fur elise")
        self.say("measures one to two")
        self.assertEqual({e.measure for e in self.window.score.loaded.exercise.events}, {"1", "2"})
        self.say("left hand")
        self.assertEqual(self.window.score.loaded.piece["hands"], "left")
        exercise = self.window.score.loaded.exercise
        self.assertEqual({e.measure for e in (*exercise.events, *exercise.rests)}, {"1", "2"})
        self.say("tempo sixty")
        self.assertEqual(self.window.playback.tempo.get(), "60")
        self.say("tempo 500")
        self.assertEqual(self.window.playback.tempo.get(), "60")
        self.assertIn("20 to 300", self.voice.messages[-1])

    def test_f1_resumes_direct_voice_actions_after_microphone_off(self):
        self.say("stop listening")
        self.assertFalse(self.window.coach.conversation)
        self.window.talk()
        self.microphone.events = ["practice ode to joy"]
        self.window.coach._poll_microphone()
        self.assertEqual(self.window.score.loaded.piece["id"], "ode_to_joy")

    def test_calibrated_take_flows_to_report_ai_and_saved_file(self):
        w = self.window
        self.say("practice ode to joy")
        self.say("calibrate hands")
        self.assertTrue(w.hands.calibrating)
        for pitch, timestamp in [(60, 10), (67, 11), (72, 12)]:
            calibration_press(w.hands, pitch, timestamp)
        self.say("finish calibration")
        self.say("record")
        started = w.score.take.started_at
        timestamp = started + .1
        camera_samples(w.hands, timestamp, [hand(64)])
        w._record(NoteEvent("on", 64, 80, 1, timestamp))
        w._record(NoteEvent("off", 64, 0, 1, timestamp + .1, .1))
        w.hands.tick(timestamp + .2)
        with patch("ada_piano.score_import.gui.monotonic", return_value=timestamp + .4):
            self.say("stop")
        summary = w.score.hand_summary()
        self.assertEqual(summary["associated"], 1)
        self.assertEqual(summary["observations"][0]["finger_name"], "index")
        [(path, error, _)] = w.sessions.flush()
        self.assertIsNone(error)
        saved = json.loads(Path(path).read_text())
        self.assertEqual(saved["hand_analysis"], summary)
        self.assertEqual(saved["mode"], "play_through")
        self.assertNotIn("hand_landmarks", saved)
        self.say("hand report")
        self.assertIn("1 of 1", self.voice.messages[-1])
        w.coach.client = FakeClient([answer("A fingertip was near one MIDI key; correct fingering is unknown.")])
        self.say("What did the camera observe?")
        self.run_gui(200)
        evidence = [m for m in w.coach.client.requests[0][0] if m.get("role") == "developer"][0]["content"]
        self.assertIn('"associated": 1', evidence)
        self.assertIn("fingertip_near_calibrated_midi_key", evidence)
        w.sessions.flush()
        saved = json.loads(Path(path).read_text())
        self.assertIn("A fingertip was near", saved["feedback"][0])

    def test_guided_session_saves_and_empty_take_does_not_block_calibration(self):
        self.say("practice ode to joy")
        self.say("guided practice")
        self.say("stop")
        [(path, error, _)] = self.window.sessions.flush()
        self.assertIsNone(error)
        self.assertEqual(json.loads(Path(path).read_text())["mode"], "guided")
        self.say("record")
        self.say("stop")
        self.say("calibrate hands")
        self.assertTrue(self.window.hands.calibrating)
        self.say("stop")
        self.assertFalse(self.window.hands.calibrating)

    def test_camera_reset_preserves_recording_and_marks_unknown(self):
        w = self.window
        self.say("practice ode to joy")
        self.say("record")
        w._record(NoteEvent("on", 64, 80, 1, monotonic()))
        w._camera_reset("Camera stopped.")
        self.assertIsNotNone(w.score.take)
        self.say("stop")
        self.assertEqual(w.score.hand_summary()["unknown_reasons"], {"calibration_reset": 1})
        self.assertTrue(w.reader.connected)

    def test_import_spoken_review_requires_explicit_approval(self):
        w = self.window
        source = Path(__file__).resolve().parents[1] / "ada_piano/exercises/five_notes.musicxml"
        with patch.dict("os.environ", {"ADA_SCORE_DIR": str(source.parent)}):
            self.say("list score files")
            self.assertIn("five_notes.musicxml", self.voice.messages[-1])
            self.say(f"import score {source}")
        self.run_gui(350)
        self.say("review passage")
        self.assertIsNone(w.score.loaded)
        self.assertIn("C4", self.voice.messages[-1])
        self.say("next measure")
        self.say("approve passage")
        self.assertIsNotNone(w.score.loaded)
        self.assertTrue(w.score.loaded.approved)

    def test_save_failure_keeps_session_and_window_open_for_retry(self):
        self.say("practice ode to joy")
        self.say("guided practice")
        with patch("ada_piano.sessions.save_session", side_effect=OSError("disk full")):
            self.window.close()
        self.assertFalse(self.window._closed)
        self.assertIsNotNone(self.window.score.session_snapshot())
        self.assertIn("still open", self.voice.messages[-1])
