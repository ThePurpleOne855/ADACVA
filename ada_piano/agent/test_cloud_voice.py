"""Cloud speech tests never call OpenAI or play real audio."""
import asyncio
import os
from pathlib import Path
from threading import Event
from types import SimpleNamespace as NS
import unittest
import wave
from unittest.mock import AsyncMock, Mock, patch

from .cloud_voice import CloudVoiceService, STYLE, DEFAULT_SPEED, playback_command, spoken_text


class CloudVoiceTests(unittest.TestCase):
    def service(self, *, chunks=None, error=None, player=None):
        paths = []
        async def play(path):
            paths.append(Path(path))
            with wave.open(str(path), "rb") as audio:
                self.assertEqual((audio.getnchannels(), audio.getsampwidth(), audio.getframerate()), (1, 2, 24000))
                self.assertEqual(audio.readframes(audio.getnframes()), b"fake-wave!")
        async def stream():
            for chunk in chunks if chunks is not None else [b"fake-wave!"]:
                yield chunk
        response = NS(iter_bytes=stream)
        context = Mock()
        context.__aenter__ = AsyncMock(return_value=response, side_effect=error)
        context.__aexit__ = AsyncMock(return_value=False)
        create = Mock(return_value=context)
        client = NS(audio=NS(speech=NS(with_streaming_response=NS(create=create))),
                    close=AsyncMock())
        factory = Mock(return_value=client)
        service = CloudVoiceService(client_factory=factory, player=player or play)
        self.addCleanup(service.close)
        return service, factory, create, client, paths

    def test_no_request_on_initialization_and_close(self):
        service, factory, _, _, _ = self.service()
        service.close()
        factory.assert_not_called()
        self.assertTrue(service.say("ignored").is_set())

    def test_parameters_session_key_and_temporary_audio_cleanup(self):
        service, factory, create, client, paths = self.service(chunks=[b"fake-", b"wave!"])
        service.configure(api_key="private-session", voice="cedar")
        with patch.dict(os.environ, {"OPENAI_API_KEY": "environment-key"}):
            self.assertTrue(service.say("Find middle C.").wait(2))
        self.assertEqual(factory.call_args.kwargs["api_key"], "private-session")
        create.assert_called_once_with(model="gpt-4o-mini-tts", voice="cedar",
                                       input="Find middle C.", instructions=STYLE,
                                       speed=DEFAULT_SPEED, response_format="pcm")
        client.close.assert_awaited_once()
        self.assertEqual(len(paths), 1)
        self.assertFalse(paths[0].exists())

    def test_missing_key_never_calls_api(self):
        service, factory, _, _, paths = self.service()
        with patch.dict(os.environ, {}, clear=True):
            self.assertTrue(service.say("Hello").wait(2))
        factory.assert_not_called()
        self.assertIn("API settings", service.status)
        self.assertEqual(paths, [])

    def test_safe_api_errors_and_retry(self):
        error = RuntimeError("private key and remote response")
        error.status_code = 401
        service, _, create, _, paths = self.service(error=error)
        service.configure(api_key="session-key")
        self.assertTrue(service.say("Hello").wait(2))
        self.assertIn("401", service.status)
        self.assertNotIn("private key", service.status)
        self.assertEqual(paths, [])
        create.return_value.__aenter__.side_effect = None
        self.assertTrue(service.say("Try again").wait(2))
        self.assertEqual(len(paths), 1)

    def test_long_speech_does_not_create_paid_request(self):
        service, factory, _, _, _ = self.service()
        self.assertTrue(service.say("x" * 4097).is_set())
        self.assertIn("4096", service.status)
        factory.assert_not_called()

    def test_empty_or_incomplete_pcm_never_plays(self):
        for chunks in ([], [b"x"]):
            service, _, _, _, paths = self.service(chunks=chunks)
            service.configure(api_key="session-key")
            self.assertTrue(service.say("Hello").wait(2))
            self.assertEqual(paths, [])
            self.assertIn("generation/download", service.status)

    def test_native_playback_failure_is_not_reported_as_auth_failure(self):
        async def fail(path):
            raise RuntimeError("private diagnostic contents")
        service, _, _, _, _ = self.service(player=fail)
        service.configure(api_key="session-key")
        self.assertTrue(service.say("Hello").wait(2))
        self.assertIn("native audio playback", service.status)
        self.assertNotIn("private diagnostic", service.status)
        self.assertNotIn("ADA AI is unavailable", service.status)

    def test_stop_cancels_download_and_never_plays(self):
        service, _, create, client, paths = self.service()
        service.configure(api_key="session-key")
        started, cancelled = Event(), Event()
        async def enter():
            started.set()
            try:
                await asyncio.sleep(30)
            finally:
                cancelled.set()
        create.return_value.__aenter__.side_effect = enter
        done = service.say("Hello")
        self.assertTrue(started.wait(2))
        service.stop()
        self.assertTrue(done.wait(1))
        self.assertTrue(cancelled.wait(2))
        service.close()
        client.close.assert_awaited_once()
        self.assertEqual(paths, [])

    def test_stop_during_playback_removes_audio(self):
        started, cancelled = Event(), Event()
        paths = []
        async def play(path):
            paths.append(path)
            started.set()
            try:
                await asyncio.sleep(30)
            finally:
                cancelled.set()
        service, _, _, _, _ = self.service(player=play)
        service.configure(api_key="session-key")
        done = service.say("Hello")
        self.assertTrue(started.wait(2))
        service.stop()
        self.assertTrue(done.wait(1))
        self.assertTrue(cancelled.wait(2))
        service.close()
        self.assertFalse(paths[0].exists())

    def test_native_audio_helper_does_not_receive_key(self):
        process = NS(wait=AsyncMock(return_value=0), returncode=0)
        service, _, _, _, _ = self.service()
        with patch("ada_piano.agent.cloud_voice.playback_command", return_value=["fake-player"]), \
             patch("asyncio.create_subprocess_exec", new=AsyncMock(return_value=process)) as launch, \
             patch.dict(os.environ, {"OPENAI_API_KEY": "secret"}):
            asyncio.run(service._play(Path("test.wav")))
        self.assertNotIn("OPENAI_API_KEY", launch.call_args.kwargs["env"])
        self.assertEqual(launch.call_args.kwargs["env"]["ADA_SPEECH_WAV"], "test.wav")

    def test_no_filename_interpolation_in_windows_script(self):
        with patch("ada_piano.agent.cloud_voice.sys.platform", "win32"), \
             patch("ada_piano.agent.cloud_voice.shutil.which", return_value="powershell.exe"):
            command = playback_command("untrusted'$filename.wav")
        self.assertNotIn("untrusted", command[-1])
        self.assertIn("$env:ADA_SPEECH_WAV", command[-1])

    def test_music_notation_is_spoken_without_changing_octaves(self):
        self.assertEqual(spoken_text("Play **C#4**, Bb3, F♯5, and E♭. Then C4."),
                         "Play C sharp four, B flat three, F sharp five, and E flat. Then C four.")
        self.assertEqual(spoken_text("A short phrase at 120 BPM."), "A short phrase at 120 BPM.")

    def test_selected_speed_and_pronunciation_reach_api(self):
        service, _, create, _, _ = self.service()
        service.configure(api_key="session-key", voice="cedar", speed=.85)
        self.assertTrue(service.say("Play C#4.").wait(2))
        self.assertEqual(create.call_args.kwargs["speed"], .85)
        self.assertEqual(create.call_args.kwargs["input"], "Play C sharp four.")

    def test_invalid_speed_rejected_before_request(self):
        service, factory, _, _, _ = self.service()
        for value in (0, 4, float("nan"), float("inf"), True, "fast"):
            with self.assertRaises(ValueError):
                service.configure(speed=value)
        factory.assert_not_called()

    def test_expanded_speech_limit_does_not_submit_request(self):
        service, factory, _, _, _ = self.service()
        self.assertTrue(service.say("C#4 " * 700).is_set())
        factory.assert_not_called()


if __name__ == "__main__":
    unittest.main()
