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
from test_playback import FakeOutputBackend, message, wait_until

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
                patch("ada_piano.note_reader.gui.has_camera", return_value=False), \
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

    def test_practice_asks_which_hand_to_start_with(self):
        w = self.window
        self.say("practice fur elise")
        self.assertIsNone(w.score.loaded)
        self.assertIn("Which hand would you like to start with?", self.voice.messages[-1])
        self.assertTrue(self.microphone.running)  # answer without saying ADA first
        self.say("say that again")
        self.assertIn("Which hand", self.voice.messages[-1])
        self.say("left")
        self.assertEqual(w.score.loaded.piece["hands"], "left")
        self.assertIn("left hand", self.voice.messages[-1])
        # A named hand or a one-hand piece loads at once; naming another piece overrides the question.
        self.say("practice fur elise right hand")
        self.assertEqual(w.score.loaded.piece["hands"], "right")
        self.say("practice fur elise")
        self.say("practice ode to joy")
        self.assertEqual((w.score.loaded.piece["id"], w.score.loaded.piece["hands"]), ("ode_to_joy", "right"))

    def test_voice_selects_devices_tempo_and_approved_measures(self):
        self.say("list MIDI inputs")
        self.assertIn("1: USB MIDI", self.voice.messages[-1])
        self.say("select MIDI input one")
        self.assertTrue(self.window.reader.connected)
        self.say("practice fur elise both hands")
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

    def record_take(self, wrong=None, late=None):
        """Simulated MIDI (FakeBackend, no hardware): play the loaded passage in time, stop, return the report."""
        w = self.window
        self.say("record")
        started, beat = w.score.take.started_at, 60 / w.score.take_tempo
        events = []
        for index, event in enumerate(w.score.loaded.exercise.events):
            onset = started + .5 + float(event.onset) * beat + (.4 if index == late else 0)
            for tone in event.tones:
                pitch = (wrong or {}).get(index, tone.pitch)
                hold = .9 * float(tone.duration) * beat
                events += [NoteEvent("on", pitch, 80, 1, onset), NoteEvent("off", pitch, 0, 1, onset + hold, hold)]
        for event in sorted(events, key=lambda e: (e.timestamp, e.kind == "on")):
            w._record(event)
        with patch("ada_piano.score_import.gui.monotonic", return_value=events[-1].timestamp + 1):
            self.say("stop")
        return w.score.performance_summary()

    def test_retry_reselects_measures_from_full_approved_passage(self):
        w = self.window

        def measures():
            exercise = w.score.loaded.exercise
            return {item.measure for item in (*exercise.events, *exercise.rests)}

        self.say("select MIDI input one")
        self.say("practice fur elise both hands")
        self.say("measures one to two")
        first = self.record_take()
        self.assertEqual((first["correct"], first["notes_expected"]), (13, 13))
        # Moving to a later passage used to fail: the 1-2 copy had replaced the approved piece.
        self.say("measures three to four")
        self.assertEqual(self.voice.messages[-1], "Selected measures 3 through 4. Say record or guided practice.")
        self.assertEqual(measures(), {"3", "4"})
        retry = self.record_take(wrong={1: 57}, late=3)
        self.assertEqual((retry["correct"], retry["wrong"], retry["late"], retry["notes_expected"]), (13, 1, 1, 14))
        self.assertEqual(retry["measure_details"], [{"measure": "3", "notes_expected": 7, "correct": 6,
            "wrong": [{"expected": "G sharp3", "played": "A3"}], "late": ["E4"]}])
        self.assertEqual(retry["clean_measures"], ["4"])
        self.assertIn("13 of 14 notes correct", self.voice.messages[-1])
        # Widening, and changing hands then re-selecting, still start from the approved piece.
        self.say("measures one to four")
        self.assertEqual(measures(), {"1", "2", "3", "4"})
        self.say("left hand")
        self.say("measures two to three")
        self.assertEqual((measures(), w.score.loaded.piece["hands"]), ({"2", "3"}, "left"))
        # Invalid ranges are spoken and leave the current selection untouched.
        for words, error in [("measures 1 to 90", "outside the approved passage"),
                             ("measures four to three", "reversed")]:
            self.say(words)
            self.assertIn(error, self.voice.messages[-1])
            self.assertEqual(measures(), {"2", "3"})

    def test_recorded_takes_are_embossed_and_text_size_follows_voice(self):
        w = self.window
        self.say("select MIDI input one")
        self.say("practice ode to joy")
        self.run_gui(60)  # the plate picks up the loaded piece on the next tick
        self.assertEqual(w.home._context["piece"], "Ode to Joy · the whole melody · right hand")
        self.record_take()
        self.record_take(wrong={5: 66})  # F sharp 4 for F 4 in measure 2
        self.assertEqual([take["score"] for take in w.home._takes], ["30 / 30", "29 / 30"])
        self.assertEqual(w.home._takes[-1]["note"], "Measure 2: F sharp 4 instead of F 4.")
        ringed = [cell["measure"] for cell in w.home._takes[-1]["cells"] if cell["ring"]]
        self.assertEqual(ringed, ["2"])
        self.say("bigger text")
        self.assertEqual((w.home.scale, self.voice.messages[-1]), (1.15, "Text size 115 percent."))
        self.say("normal text")
        self.assertEqual(w.home.scale, 1.0)
        self.say("measures one to two")
        self.run_gui(60)
        self.assertEqual(w.home._context["piece"], "Ode to Joy · measures 1 to 2 · right hand")
        self.assertEqual(w.home._takes, [])  # a new passage starts a fresh comparison

    def test_f1_resumes_direct_voice_actions_after_microphone_off(self):
        self.say("stop listening")
        self.assertFalse(self.window.coach.conversation)
        self.window.talk()
        self.microphone.events = ["practice ode to joy"]
        self.window.coach._poll_microphone()
        self.assertEqual(self.window.score.loaded.piece["id"], "ode_to_joy")

    def test_wake_prefixed_finish_is_accepted_while_recording(self):
        self.say("practice ode to joy")
        self.say("record")
        self.window._record(NoteEvent("on", 64, 80, 1, monotonic()))
        self.window.coach.hands_free.set(True)
        self.window.coach._poll_microphone()  # switches into guarded capture
        self.microphone.events = ["finish recording", "ADA record", "ADA finish recording"]
        self.window.coach._poll_microphone()
        self.assertIsNone(self.window.score.take)
        self.assertEqual(self.window.score.performance_summary()["outcome"], "stopped_early")
        self.assertIn("stopped early", self.voice.messages[-1])
        self.assertTrue(self.window.reader.connected)

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


THROUGH = "Midi Through:Midi Through Port-0 14:0"
SYNTH = "FLUID Synth (4321):Synth input port (4321:0) 128:0"
PIANO = "Digital Piano:Digital Piano MIDI 1 24:0"  # a USB piano: same ALSA port for input and output


@unittest.skipIf(existing.tk is None, "Tk unavailable")
class PianoAutoSetupTests(unittest.TestCase):
    """Plug-and-play MIDI setup. Simulated ports only (FakeBackend/FakeOutputBackend), using Linux ALSA names."""
    run_gui = existing.NoteReaderGuiTests.run_gui
    close_window = AccessibleIntegrationTests.close_window

    def open(self, inputs, outputs):
        try:
            self.root = existing.tk.Tk()
        except existing.tk.TclError as exc:
            self.skipTest(str(exc))
        self.root.withdraw()
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.backend, self.outputs, self.voice = FakeBackend(), FakeOutputBackend(), FakeVoice()
        self.backend.names, self.outputs.names = list(inputs), list(outputs)
        with patch("ada_piano.camera.gui.best_camera", return_value=(0, "Camera 0")), \
                patch("ada_piano.note_reader.gui.has_camera", return_value=False), \
                patch("ada_piano.agent.gui.CoachPanel.use_best_voice"):
            self.window = existing.NoteReaderWindow(self.root, reader=NoteReader(self.backend),
                player=ReferencePlayer(self.outputs, message_factory=message),
                camera_worker=existing.FakeCameraWorker(), voice=self.voice, microphone=FakeMicrophone(),
                accessible=True, session_directory=temp.name)
        self.addCleanup(self.close_window)
        return self.window

    def test_opening_with_piano_connects_it_and_sends_reference_to_it(self):
        w = self.open([THROUGH, PIANO], [THROUGH, SYNTH, PIANO])
        self.assertEqual(w.reader.port_name, PIANO)
        self.assertEqual(w.playback.output.get(), PIANO)  # not the first software synth
        self.assertIn("Piano connected. I'll play reference sound through it too.", self.voice.messages)

    def test_piano_plugged_in_after_opening_is_found_and_paired(self):
        w = self.open([THROUGH], [THROUGH])
        self.assertFalse(w.reader.connected)
        self.assertEqual(w.playback.output.get(), "")
        self.backend.names, self.outputs.names = [THROUGH, PIANO], [THROUGH, SYNTH, PIANO]
        w._next_scan = 0
        self.run_gui(60)
        self.assertEqual((w.reader.port_name, w.playback.output.get()), (PIANO, PIANO))
        self.assertEqual(self.voice.messages[-1], "Piano connected. I'll play reference sound through it too.")

    def test_replug_with_new_port_number_still_plays_reference(self):
        moved = PIANO.replace("24:0", "28:0")
        w = self.open([PIANO], [PIANO])
        self.backend.names = self.outputs.names = []
        w._check_due = 0
        self.run_gui(60)
        self.assertFalse(w.reader.connected)
        self.assertIn("disconnected", self.voice.messages[-1])
        self.backend.names, self.outputs.names = [moved], [moved]
        w._next_scan = 0
        self.run_gui(60)
        self.assertEqual((w.reader.port_name, w.playback.output.get()), (moved, moved))
        w.playback.play_note(60)
        wait_until(lambda: w.playback.player.status.state != "playing")
        self.assertEqual(w.playback.player.status.state, "finished", w.playback.player.status.detail)
        self.assertEqual([m.note for m in self.outputs.port.messages if m.type == "note_on"], [60])

    def test_software_ports_are_not_the_piano_and_input_only_device_keeps_output(self):
        keyboard = "USB Keyboard:USB Keyboard MIDI 1 20:0"  # sends notes but has no output port
        w = self.open([THROUGH, "RtMidiOut Client:RtMidi output 130:0", keyboard], [THROUGH, SYNTH])
        self.assertEqual(w.reader.port_name, keyboard)
        self.assertEqual(w.playback.output.get(), SYNTH)
        self.assertIn("Piano connected.", self.voice.messages)
        self.assertNotIn("Piano connected. I'll play reference sound through it too.", self.voice.messages)

    def test_device_name_matches_input_and_output_ports(self):
        device = existing.NoteReaderWindow._device
        self.assertEqual(device(PIANO), "digital piano")
        self.assertEqual(device("mioXC:mioXC MIDI 1 36:0"), "mioxc")
        self.assertEqual(device("Digital Piano 0"), device("Digital Piano 1"))  # Windows-style names (simulated)
