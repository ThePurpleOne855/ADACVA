"""Offline natural voice, camera selection without phone drivers, and coach-chosen sound."""
from pathlib import Path
import tempfile
from threading import Event
import unittest
from unittest.mock import patch

import test_note_reader_gui as existing
from test_accessible_flow import ODE
from test_agent import FakeClient, answer, call
from test_agent_gui import FakeVoice

from ada_piano.agent.tools import AgentTools
from ada_piano.camera.devices import best_camera, camera_choices
from ada_piano.camera.source import parse_camera_source
from ada_piano.voice import piper_tts


def sysfs(devices):
    root = Path(tempfile.mkdtemp())
    for number, name, index in devices:
        folder = root / f"video{number}"
        folder.mkdir()
        (folder / "name").write_text(name)
        (folder / "index").write_text(str(index))
    return root


class CameraSelectionTests(unittest.TestCase):
    def test_prefers_usb_webcam_and_skips_virtual_and_metadata_nodes(self):
        root = sysfs([(0, "Integrated Camera", 0), (1, "Integrated Camera", 1),
                      (2, "Dummy video device (0x0000)", 0), (4, "CyberTrack H4", 0), (5, "CyberTrack H4", 1)])
        self.assertEqual(list(camera_choices(root).values()), [0, 2, 4])
        self.assertEqual(best_camera(root, environ={}), (4, "CyberTrack H4"))

    def test_built_in_when_alone_and_environment_override(self):
        root = sysfs([(0, "Integrated Camera", 0), (2, "Dummy video device (0x0000)", 0)])
        self.assertEqual(best_camera(root, environ={})[0], 0)
        self.assertEqual(best_camera(root, environ={"ADA_CAMERA": "192.168.1.20:8080"})[0],
                         "http://192.168.1.20:8080/video")

    def test_phone_addresses(self):
        self.assertEqual(parse_camera_source("10.0.0.7:4747"), "http://10.0.0.7:4747/video")
        self.assertEqual(parse_camera_source("http://10.0.0.7:8081/live"), "http://10.0.0.7:8081/live")
        self.assertEqual(parse_camera_source(" 3 "), 3)


class FakePiper:
    def __init__(self):
        self.texts = []

    def synthesize_wav(self, text, output):
        self.texts.append(text)
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(22050)
        output.writeframes(b"\0\0" * 10)


class PiperTests(unittest.TestCase):
    def test_note_names_are_spoken_naturally(self):
        self.assertEqual(piper_tts.spoken("Play F sharp4, then C#5 and Bb3. **ADA**"),
                         "Play F sharp 4, then C sharp 5 and B flat 3. Ada")

    def test_speaks_through_player_and_stop_cancels(self):
        fake = FakePiper()
        service = piper_tts.PiperVoiceService("model.onnx", player=lambda path: ["true"], loader=lambda path: fake)
        self.addCleanup(service.close)
        self.assertTrue(service.available)
        self.assertTrue(service.say("Hello C4").wait(5))
        self.assertEqual(fake.texts, ["Hello C 4"])
        slow = piper_tts.PiperVoiceService("model.onnx", player=lambda path: ["sleep", "5"], loader=lambda path: fake)
        self.addCleanup(slow.close)
        done = slow.say("long")
        slow.stop()
        self.assertTrue(done.wait(3))

    def test_missing_model_reports_setup_command(self):
        with patch.dict("os.environ", {"ADA_PIPER_VOICE": "/nonexistent/voice.onnx"}):
            service = piper_tts.PiperVoiceService(player=lambda path: ["true"])
        self.addCleanup(service.close)
        self.assertFalse(service.available)
        self.assertIn("voice-setup", service.status)


class SoundToolTests(unittest.TestCase):
    def test_play_notes_validation(self):
        calls = []
        tools = AgentTools(None, action=lambda name, args: calls.append(args) or {"status": "queued"})
        tools.dispatch("play_notes", {"notes": "C4 E4 G4", "chord": True, "tempo": 60})
        self.assertEqual([n.start_beat for n in calls[0]["plan"]], [0, 0, 0])
        for bad in ({"notes": "C4 " * 17, "chord": False, "tempo": 60},
                    {"notes": "C9", "chord": False, "tempo": 60},
                    {"notes": "C4", "chord": "yes", "tempo": 60},
                    {"notes": "C4", "chord": False, "tempo": 500}):
            with self.assertRaises(ValueError):
                tools.dispatch("play_notes", bad)
        self.assertEqual(tools.dispatch("replay_my_playing", {}), {"status": "no_play_through"})


@unittest.skipIf(existing.tk is None, "Tk unavailable")
class WindowTests(unittest.TestCase):
    setUp = existing.NoteReaderGuiTests.setUp
    close_window = existing.NoteReaderGuiTests.close_window
    run_gui = existing.NoteReaderGuiTests.run_gui

    def coach(self, client=None):
        coach = self.window.coach
        coach.voice.close()
        coach.voice = FakeVoice()
        coach.client = client
        coach.speak.set(True)
        self.window.accessible = True
        return coach

    def test_greeting_asks_what_to_practice_and_lists_catalog(self):
        coach = self.coach()
        self.window.greet()
        said = coach.voice.messages[-1]
        self.assertIn("What would you like to practice today?", said)
        self.assertIn("Für Elise", said)
        self.assertIn("Ode to Joy", said)

    def test_coach_plays_a_chord_without_a_dialog(self):
        coach = self.coach(FakeClient([call("play_notes", {"notes": "C4 E4 G4", "chord": True, "tempo": 60}),
                                       answer("That was C major.")]))
        coach.text.set("What does a C major chord sound like?")
        with patch.object(self.window.playback, "play_plan") as play, \
                patch("ada_piano.agent.gui.messagebox.askyesno") as dialog:
            coach.ask()
            self.run_gui(300)
        dialog.assert_not_called()
        self.assertEqual([n.note for n in play.call_args.args[0]], [60, 64, 67])
        self.assertIn("Here's the chord", coach.transcript.get("1.0", "end"))

    def test_replay_own_take_by_voice(self):
        coach = self.coach()
        coach.text.set("practice ode to joy")
        coach.ask()
        self.window.score.play_through()
        port = self.backend.ports[-1]
        for pitch in ODE[:8]:
            port.messages.extend([existing.note(number=pitch), existing.note("note_off", number=pitch)])
        self.run_gui(120)
        self.window.score.finish_take()
        with patch.object(self.window.playback, "play_plan") as play:
            coach.text.set("replay")
            coach.ask()
            self.run_gui(120)
        self.assertEqual([n.note for n in play.call_args.args[0]], ODE[:8])
        self.assertEqual(play.call_args.args[1], 60)

    def test_camera_by_voice_announces_progress(self):
        coach = self.coach()
        with patch.object(self.window.camera, "auto_start", return_value="CyberTrack H4"):
            coach.text.set("start camera")
            coach.ask()
        self.assertIn("Starting the camera: CyberTrack H4", coach.voice.messages[-1])
        self.window.camera.status.set("Camera 4: Tracking 2 hand(s).")
        self.window._watch_camera()
        self.assertEqual(coach.voice.messages[-1], "Camera is on. I can see 2 hands.")


if __name__ == "__main__":
    unittest.main()
