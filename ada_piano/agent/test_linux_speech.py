"""Linux voice lifecycle and capture tests; no real audio or network requests."""
import asyncio
import io
import os
import struct
from threading import Event
from types import SimpleNamespace as NS
import unittest
from unittest.mock import AsyncMock, Mock, patch
import wave

from .linux_speech_input import LinuxSpeechInput, Utterance, recording_command
from .cloud_voice import playback_command


class LinuxSpeechTests(unittest.TestCase):
    def service(self, recorder=None, create=None):
        recorder = recorder or AsyncMock(return_value=b"wave-data")
        create = create or AsyncMock(return_value=NS(text="ADA, where is middle C?"))
        client = NS(audio=NS(transcriptions=NS(create=create)), close=AsyncMock())
        factory = Mock(return_value=client)
        service = LinuxSpeechInput(recorder=recorder, client_factory=factory)
        service.configure(api_key="session-secret")
        self.addCleanup(service.close)
        return service, recorder, factory, client

    def test_one_shot_uses_session_key_and_returns_text(self):
        service, _, factory, client = self.service()
        with patch.dict(os.environ, {"OPENAI_API_KEY": "environment-secret"}):
            self.assertTrue(service.start())
            service._future.result(2)
        self.assertEqual(service.drain(), ["ADA, where is middle C?"])
        self.assertEqual(factory.call_args.kwargs["api_key"], "session-secret")
        self.assertEqual(client.audio.transcriptions.create.call_args.kwargs["file"],
                         ("question.wav", b"wave-data", "audio/wav"))
        client.close.assert_awaited_once()

    def test_missing_key_never_records(self):
        service, recorder, factory, _ = self.service()
        service.configure(api_key=None)
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(service.start())
        recorder.assert_not_called()
        factory.assert_not_called()
        self.assertIn("API settings", service.status)

    def test_silence_never_uploads(self):
        service, _, factory, _ = self.service(recorder=AsyncMock(return_value=None))
        service.start()
        service._future.result(2)
        factory.assert_not_called()
        self.assertEqual(service.drain(), [])
        self.assertIn("No speech", service.status)

    def test_gate_ignores_silence_and_clicks_and_builds_wav(self):
        quiet = b"\0" * 3200
        loud = struct.pack("<1600h", *([1000, -1000] * 800))
        gate = Utterance()
        for _ in range(120):
            gate.feed(quiet)
        self.assertIsNone(gate.wav())
        self.assertLessEqual(len(gate.pre_roll), 3)
        gate.feed(loud)
        for _ in range(10):
            gate.feed(quiet)
        self.assertIsNone(gate.wav())
        gate = Utterance()
        gate.feed(quiet)
        for _ in range(5):
            self.assertFalse(gate.feed(loud))
        for _ in range(9):
            self.assertFalse(gate.feed(quiet))
        self.assertTrue(gate.feed(quiet))
        with wave.open(io.BytesIO(gate.wav())) as audio:
            self.assertEqual((audio.getnchannels(), audio.getframerate(), audio.getsampwidth()), (1,16000,2))

    def test_stop_cancels_recording_without_upload(self):
        started, cancelled = Event(), Event()
        async def record():
            started.set()
            try:
                await asyncio.sleep(30)
            finally:
                cancelled.set()
        service, _, factory, _ = self.service(recorder=record)
        service.start()
        self.assertTrue(started.wait(2))
        service.stop()
        self.assertTrue(cancelled.wait(2))
        factory.assert_not_called()
        self.assertEqual(service.drain(), [])

    def test_stop_during_transcription_discards_late_result(self):
        started, cancelled = Event(), Event()
        async def transcribe(**kwargs):
            started.set()
            try:
                await asyncio.sleep(30)
            except asyncio.CancelledError:
                cancelled.set()
                return NS(text="ADA late command")
        service, _, _, client = self.service(create=transcribe)
        service.start()
        self.assertTrue(started.wait(2))
        service.stop()
        self.assertTrue(cancelled.wait(2))
        service.close()
        self.assertEqual(service.drain(), [])
        client.close.assert_awaited_once()

    def test_error_safe_retry_and_close(self):
        error = RuntimeError("session-secret remote body")
        error.status_code = 401
        create = AsyncMock(side_effect=error)
        service, _, _, _ = self.service(create=create)
        service.start()
        service._future.result(2)
        self.assertFalse(service.available)
        self.assertIn("401", service.status)
        self.assertNotIn("session-secret", service.status)
        create.side_effect = None
        create.return_value = NS(text="Try again")
        self.assertTrue(service.start(retry=True))
        service._future.result(2)
        self.assertEqual(service.drain(), ["Try again"])
        service.close()
        self.assertFalse(service.start(retry=True))

    def test_continuous_mode_records_again_and_cancels(self):
        waiting = Event()
        count = 0
        async def record():
            nonlocal count
            count += 1
            if count == 1:
                return b"wave-data"
            waiting.set()
            await asyncio.sleep(30)
        service, _, _, _ = self.service(recorder=record)
        service.start(continuous=True)
        self.assertTrue(waiting.wait(2))
        self.assertEqual(service.drain(), ["ADA, where is middle C?"])
        service.stop()

    def test_pipewire_target_and_playback_fallback(self):
        with patch("ada_piano.agent.cloud_voice.sys.platform", "linux"), \
             patch("shutil.which", side_effect=lambda name: "/usr/bin/"+name), \
             patch.dict(os.environ, {"ADA_MIC_TARGET": "physical-mic"}):
            command = recording_command()
            self.assertIn("physical-mic", command)
            self.assertIn("--raw", command)
            self.assertEqual(playback_command("voice.wav"), ["/usr/bin/pw-play", "voice.wav"])
        with patch("ada_piano.agent.cloud_voice.sys.platform", "linux"), \
             patch("shutil.which", side_effect=lambda name: "/usr/bin/"+name if name in {"arecord", "aplay"} else None):
            self.assertIn("S16_LE", recording_command())
            self.assertEqual(playback_command("voice.wav"), ["/usr/bin/aplay", "voice.wav"])

    def test_capture_strips_key_and_terminates_recorder(self):
        service, _, _, _ = self.service()
        reader = NS(readexactly=AsyncMock(return_value=b"\0" * 3200))
        process = NS(stdout=reader, returncode=None, terminate=Mock(), wait=AsyncMock(return_value=0))
        with patch("ada_piano.agent.linux_speech_input.recording_command", return_value=["fake"]), \
             patch("asyncio.create_subprocess_exec", new=AsyncMock(return_value=process)) as launch, \
             patch.dict(os.environ, {"OPENAI_API_KEY": "secret"}):
            self.assertIsNone(asyncio.run(service._capture()))
        self.assertNotIn("OPENAI_API_KEY", launch.call_args.kwargs["env"])
        process.terminate.assert_called_once()

    def test_capture_cancellation_reaps_process(self):
        service, _, _, _ = self.service()
        process = NS(returncode=None, terminate=Mock(), wait=AsyncMock(return_value=0))
        async def check():
            started = asyncio.Event()
            async def read(size):
                started.set()
                await asyncio.sleep(30)
            process.stdout = NS(readexactly=read)
            with patch("ada_piano.agent.linux_speech_input.recording_command", return_value=["fake"]), \
                 patch("asyncio.create_subprocess_exec", new=AsyncMock(return_value=process)):
                task = asyncio.create_task(service._capture())
                await asyncio.wait_for(started.wait(), 1)
                task.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await task
        asyncio.run(check())
        process.terminate.assert_called_once()
        process.wait.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
