"""Offline diagnostics, microphone lifecycle and standalone chat regressions."""
import io
import os
from threading import Event
from types import SimpleNamespace as NS
import unittest
from unittest.mock import AsyncMock, Mock, patch

from .coach import AgentSetupError, Coach, OpenAIClient, error_message
from .speech_input import SpeechInput, voice_command
from .tools import AgentTools


class InputTests(unittest.TestCase):
    def test_connection_errors_do_not_expose_key_or_response(self):
        for status, code, expected in [(401, None, "replace"), (403, None, "permissions"),
                                       (404, None, "model"), (429, "insufficient_quota", "credit"),
                                       (429, None, "rate limit"), (400, None, "format"),
                                       (500, None, "server")]:
            error = RuntimeError("sk-secret credential and private API response")
            error.status_code, error.code = status, code
            message = error_message(error)
            self.assertIn(expected, message)
            self.assertNotIn("sk-secret", message)
            self.assertNotIn("private API", message)
        self.assertIn("API settings", error_message(AgentSetupError("key", "secret")))

    def test_session_credentials_override_environment(self):
        sdk = NS(OpenAI=Mock())
        with patch.dict("sys.modules", {"openai": sdk}), patch.dict(os.environ, {"OPENAI_API_KEY": "env-only"}):
            client = OpenAIClient(api_key="session-only", model="session-model")
        self.assertEqual(sdk.OpenAI.call_args.kwargs["api_key"], "session-only")
        self.assertEqual(client.model, "session-model")
        client.close()

    def test_general_chat_without_score_or_hardware(self):
        client = NS(respond=Mock(return_value=NS(output=[], output_text="Start with middle C.")))
        coach = Coach(AgentTools(None), client)
        self.assertEqual(coach.ask("How do I start learning piano?"), "Start with middle C.")
        with self.assertRaises(ValueError):
            coach.tools.dispatch("start_practice", {"start_measure": "1", "end_measure": "1"})

    def test_wake_phrase_requires_prefix_and_complete_question(self):
        self.assertEqual(voice_command("Hey ADA, how do I find C?"), ("ask", "how do I find C?"))
        self.assertEqual(voice_command("Ada stop listening."), ("stop", ""))
        for text in ("ADA", "tell ADA to play", "adagio", "background conversation"):
            self.assertIsNone(voice_command(text))

    def service(self, lines, code=0):
        process = Mock()
        process.stdout = io.BytesIO(lines)
        process.wait.return_value = code
        process.poll.return_value = code
        popen = Mock(return_value=process)
        service = SpeechInput(command=["fake"], popen=popen)
        self.addCleanup(service.close)
        return service, process, popen

    def test_transcript_confidence_and_no_credentials_in_helper(self):
        lines = (b'{"kind":"ready"}\n'
                 b'{"kind":"text","text":"ADA help me","confidence":0.9}\n'
                 b'{"kind":"text","text":"wrong words","confidence":0.1}\n')
        service, _, popen = self.service(lines)
        with patch.dict(os.environ, {"OPENAI_API_KEY": "secret"}):
            service.start(continuous=True)
            service._thread.join(1)
        self.assertEqual(service.drain(), ["ADA help me"])
        self.assertNotIn("OPENAI_API_KEY", popen.call_args.kwargs["env"])
        self.assertEqual(popen.call_args.kwargs["env"]["ADA_MIC_CONTINUOUS"], "1")

    def test_error_falls_back_to_text_and_explicit_retry(self):
        service, process, _ = self.service(b'{"kind":"error"}\n', code=1)
        service.start()
        service._thread.join(1)
        self.assertFalse(service.available)
        self.assertIn("permissions", service.status)
        process.stdout = io.BytesIO(b'{"kind":"silence"}\n')
        process.wait.return_value = process.poll.return_value = 0
        self.assertTrue(service.start(retry=True))
        service._thread.join(1)
        self.assertTrue(service.available)

    def test_stop_discards_old_microphone_events(self):
        service, _, _ = self.service(b'{"kind":"text","text":"late","confidence":0.9}\n')
        service.start()
        service._thread.join(1)
        service.stop()
        self.assertEqual(service.drain(), [])

    def test_closed_microphone_never_restarts(self):
        service, _, popen = self.service(b'')
        service.close()
        self.assertFalse(service.start(retry=True))
        popen.assert_not_called()


class FakeVoice:
    status = "Fake speech ready."
    def say(self, text):
        event = Event()
        event.set()
        return event
    def stop(self):
        pass
    def close(self):
        pass


class FakeMicrophone:
    available = True
    running = False
    status = "Microphone off."
    def __init__(self):
        self.events = []
        self.closed = False
    def start(self, **kwargs):
        self.running = True
        return True
    def stop(self):
        self.running = False
        self.events.clear()
    def close(self):
        self.closed = True
        self.stop()
    def drain(self):
        events, self.events = self.events, []
        return events


class StandaloneGuiTests(unittest.TestCase):
    def setUp(self):
        try:
            import tkinter as tk
        except ImportError:
            self.skipTest("Desktop Tk unavailable")
        try:
            self.root = tk.Tk()
        except tk.TclError:
            self.skipTest("Desktop Tk unavailable")
        self.root.withdraw()
        from .gui import CoachPanel
        self.microphone = FakeMicrophone()
        self.client = NS(respond=Mock(return_value=NS(output=[], output_text="Start with middle C.")))
        self.panel = CoachPanel(self.root, client=self.client, voice=FakeVoice(), microphone=self.microphone)
        self.panel.pack(fill="both", expand=True)
        self.addCleanup(self.close)

    def close(self):
        self.panel.close()
        self.root.destroy()

    def settle(self):
        self.panel._thread.join(1)
        self.panel.after_cancel(self.panel._timer)
        self.panel._poll()

    def test_standalone_question_without_approved_score(self):
        self.panel.text.set("How do I start?")
        self.panel.ask()
        self.settle()
        self.assertIn("Start with middle C", self.panel.transcript.get("1.0", "end"))

    def test_settings_and_labelled_input_present(self):
        self.microphone.configure = Mock()
        self.assertIn("API key:", self.panel.connection.get())
        self.assertEqual(self.panel.entry.cget("textvariable"), str(self.panel.text))
        self.panel.api_settings()
        import tkinter as tk
        dialog = next(c for c in self.panel.winfo_children() if isinstance(c, tk.Toplevel))
        entries = [c for c in dialog.winfo_children()[0].winfo_children() if c.winfo_class() == "TEntry"]
        self.assertEqual(entries[0].cget("show"), "•")
        entries[0].insert(0, "private-session-key")
        entries[1].delete(0, "end")
        entries[1].insert(0, "chosen-model")
        apply = next(c for c in dialog.winfo_children()[0].winfo_children() if c.winfo_class() == "TButton")
        apply.invoke()
        self.assertEqual(self.panel._api_key, "private-session-key")
        self.microphone.configure.assert_called_once_with(api_key="private-session-key")
        self.assertEqual(self.panel._model, "chosen-model")
        self.assertNotIn("private-session-key", self.panel.connection.get())

    def test_one_shot_speech_fills_input_without_sending(self):
        self.panel.listen()
        self.microphone.events = ["how do I find middle C"]
        self.panel._poll_microphone()
        self.assertEqual(self.panel.text.get(), "how do I find middle C")
        self.client.respond.assert_not_called()

    def test_hands_free_requires_wake_phrase_and_can_stop(self):
        self.panel.hands_free.set(True)
        self.microphone.events = ["ordinary background speech"]
        self.panel._poll_microphone()
        self.client.respond.assert_not_called()
        self.microphone.events = ["ADA how do I start"]
        self.panel._poll_microphone()
        self.settle()
        self.client.respond.assert_called_once()
        self.microphone.events = ["ADA stop"]
        self.panel._poll_microphone()
        self.assertFalse(self.panel.hands_free.get())
        self.assertTrue(self.panel._cancel.is_set())

    def test_microphone_pauses_during_spoken_response(self):
        self.panel.hands_free.set(True)
        self.panel._speech_done = Event()
        self.panel._poll_microphone()
        self.assertFalse(self.microphone.running)
        self.assertIn("paused", self.panel.microphone_status.get())

    def test_cloud_speech_receives_session_key_and_selected_voice(self):
        from .cloud_voice import CloudVoiceService
        self.panel.voice = CloudVoiceService(player=AsyncMock())
        self.panel._api_key = "private-session-key"
        self.panel.voice_choice.set("cedar")
        self.panel.voice_speed.set("0.85")
        done = Event()
        done.set()
        with patch.object(self.panel.voice, "say", return_value=done) as say:
            self.panel._say("Hello")
        say.assert_called_once_with("Hello")
        self.assertEqual(self.panel.voice._api_key, "private-session-key")
        self.assertEqual(self.panel.voice._voice, "cedar")
        self.assertEqual(self.panel.voice._speed, .85)
        self.assertNotIn("private-session-key", self.panel.transcript.get("1.0", "end"))

    def test_preview_pauses_microphone_without_sending_chat(self):
        from .cloud_voice import PREVIEW_TEXT
        self.microphone.start()
        with patch.object(self.panel.voice, "say", return_value=Event()) as say:
            self.panel.preview_voice()
        say.assert_called_once_with(PREVIEW_TEXT)
        self.assertFalse(self.microphone.running)
        self.assertFalse(self.panel.speak.get())
        self.client.respond.assert_not_called()
        self.panel._poll_microphone()
        self.assertIn("paused", self.panel.microphone_status.get())

    def test_preview_does_not_interrupt_reference_playback(self):
        self.panel._pending_reference = object()
        with patch.object(self.panel.voice, "say") as say:
            self.panel.preview_voice()
        say.assert_not_called()

    def test_voice_selector_switches_between_local_and_cloud(self):
        from ada_piano.voice import VoiceService
        from .cloud_voice import CloudVoiceService
        self.panel._injected_voice = False
        self.panel.voice_choice.set("System (local)")
        self.panel._voice_changed()
        self.assertIsInstance(self.panel.voice, VoiceService)
        self.panel.voice_choice.set("marin")
        self.panel._voice_changed()
        self.assertIsInstance(self.panel.voice, CloudVoiceService)
        self.assertFalse(self.panel.speak.get())

    def test_input_remains_visible_at_small_window_size(self):
        self.root.geometry("800x560")
        self.root.deiconify()
        self.root.update()
        entry = self.panel.entry
        y = entry.winfo_rooty() - self.root.winfo_rooty()
        self.assertTrue(entry.winfo_ismapped())
        self.assertGreaterEqual(entry.winfo_height(), 30)
        self.assertGreaterEqual(y, 0)
        self.assertLess(y + entry.winfo_height(), self.root.winfo_height())

    def test_voice_stop_cancels_delayed_model_reply(self):
        started, release = Event(), Event()
        def respond(*args):
            started.set()
            release.wait(2)
            return NS(output=[], output_text="Late reply")
        self.client.respond.side_effect = respond
        self.panel.text.set("Help")
        self.panel.ask()
        self.assertTrue(started.wait(1))
        self.panel.hands_free.set(True)
        self.microphone.events = ["ADA stop"]
        self.panel._poll_microphone()
        release.set()
        self.settle()
        self.assertNotIn("Late reply", self.panel.transcript.get("1.0", "end"))

    def test_missing_key_has_actionable_message(self):
        self.panel.client = None
        with patch.dict(os.environ, {}, clear=True):
            self.panel.text.set("Help")
            self.panel.ask()
            self.settle()
        text = self.panel.transcript.get("1.0", "end")
        self.assertIn("no API key", text)
        self.assertIn("API settings", text)


if __name__ == "__main__":
    unittest.main()
