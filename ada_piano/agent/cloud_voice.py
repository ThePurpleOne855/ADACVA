"""Opt-in OpenAI speech, with cancellable network and native WAV playback."""
import asyncio
import os
import math
import re
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import wave
from threading import Event, Lock, Thread

from .coach import AgentSetupError, error_message


VOICES = ("marin", "cedar", "coral", "alloy", "ash", "ballad", "echo",
          "fable", "nova", "onyx", "sage", "shimmer", "verse")
DEFAULT_VOICE = "cedar"
DEFAULT_SPEED = 0.95
STYLE = (
    "Speak in clear, conversational English, as a piano teacher talking to an adult beside them. "
    "Use a relaxed, grounded voice with natural sentence rhythm and gentle variation in intonation. "
    "Articulate note names distinctly and leave a short pause between an explanation and an action. "
    "Keep a comfortable, steady pace. Avoid whispering, breathiness, exaggerated cheerfulness, "
    "sing-song delivery, a theatrical narrator voice, and drawn-out syllables. "
    "Pronounce ADA as the name Ay-duh, not individual letters. Read only the supplied words."
)
PREVIEW_TEXT = "Hi, I'm Ada. Let's take this one step at a time. Find middle C, then play C4, D4, and E4. Take your time."


def spoken_text(text):
    """Expand music notation for speech while preserving the displayed reply."""
    numbers = ("zero", "one", "two", "three", "four", "five", "six", "seven", "eight")
    def note(match):
        letter, accidental, octave = match.groups()
        suffix = {"#": " sharp", "♯": " sharp", "b": " flat", "♭": " flat", "": ""}[accidental]
        return letter + suffix + (" " + numbers[int(octave)] if octave else "")
    text = re.sub(r"\b([A-G])([#♯b♭]?)([0-8])(?!\w)", note, text)
    text = re.sub(r"\b([A-G])([#♯b♭])()(?!\w)", note, text)
    text = re.sub(r"\[([^\]]+)\]\(https?://[^)]+\)", r"\1", text)
    text = re.sub(r"\*\*(.+?)\*\*|__(.+?)__", lambda m: m.group(1) or m.group(2), text)
    return text.replace("`", "")


def playback_command(path):
    """Native playback only; no extra Python audio dependency."""
    if sys.platform == "win32":
        engine = shutil.which("powershell.exe")
        script = ("$ErrorActionPreference='Stop'; "
                  "$sound=New-Object System.Media.SoundPlayer($env:ADA_SPEECH_WAV); "
                  "try { $sound.PlaySync() } finally { $sound.Dispose() }")
        return [engine, "-NoProfile", "-NonInteractive", "-Command", script] if engine else None
    engine = (shutil.which("afplay") if sys.platform == "darwin" else
              (shutil.which("pw-play") or shutil.which("aplay")))
    return [engine, str(path)] if engine else None


class CloudVoiceService:
    """Same say/stop/close contract as local VoiceService; never touches Tk."""
    def __init__(self, *, client_factory=None, player=None):
        self.available = bool(playback_command("probe.wav"))
        self.status = "OpenAI AI-generated speech ready (API charges apply)." if self.available else "Audio player unavailable; continuing in text mode."
        self._client_factory = client_factory
        self._player = player or self._play
        if player is not None:
            self.available = True
        self._lock = Lock()
        self._generation = 0
        self._closed = False
        self._future = None
        self._loop = asyncio.new_event_loop()
        self._thread = Thread(target=self._run, name="ada-cloud-voice", daemon=True)
        self._thread.start()
        self._api_key = None
        self._voice = DEFAULT_VOICE
        self._speed = DEFAULT_SPEED

    def configure(self, *, api_key=None, voice=DEFAULT_VOICE, speed=DEFAULT_SPEED):
        if voice not in VOICES:
            raise ValueError("Unknown speech voice")
        if isinstance(speed, bool) or not isinstance(speed, (int, float)) or not math.isfinite(speed) or not .75 <= speed <= 1.15:
            raise ValueError("Speech speed must be between 0.75 and 1.15")
        with self._lock:
            self._api_key, self._voice = api_key, voice
            self._speed = float(speed)

    def say(self, text, *, replace=True):
        done = Event()
        with self._lock:
            if self._closed or not self.available:
                done.set()
                return done
            # One utterance retained, matching the coach's replaceable speech.
            self._cancel_locked()
            if not isinstance(text, str) or not text.strip() or len(text) > 4096:
                self.status = "Speech requires 1–4096 characters; the full response remains in chat."
                done.set()
                return done
            text = spoken_text(text)
            if len(text) > 4096:
                self.status = "Spoken text exceeds 4096 characters; read the full response in chat."
                done.set()
                return done
            key = self._api_key or os.environ.get("OPENAI_API_KEY")
            future = asyncio.run_coroutine_threadsafe(
                self._speak(text, key, self._voice, self._speed, self._generation), self._loop)
            self._future = future
            future.add_done_callback(lambda result: done.set())
        return done

    def _cancel_locked(self):
        self._generation += 1
        if self._future is not None:
            self._future.cancel()
            self._future = None

    def stop(self):
        with self._lock:
            self._cancel_locked()

    def close(self):
        with self._lock:
            if self._closed:
                return
            self._closed = True
            self._cancel_locked()
            self._api_key = None
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join(timeout=2)

    def _run(self):
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_forever()
        finally:
            tasks = asyncio.all_tasks(self._loop)
            for task in tasks:
                task.cancel()
            self._loop.run_until_complete(asyncio.gather(*tasks, return_exceptions=True))
            self._loop.close()

    def _current(self, generation):
        with self._lock:
            return generation == self._generation and not self._closed

    def _status(self, generation, message):
        with self._lock:
            if generation == self._generation and not self._closed:
                self.status = message

    async def _speak(self, text, key, voice, speed, generation):
        client = None
        stage = "API setup"
        try:
            if not self._current(generation):
                return
            if not key:
                raise AgentSetupError("key", "Missing key")
            factory = self._client_factory
            if factory is None:
                try:
                    from openai import AsyncOpenAI
                except ImportError as exc:
                    raise AgentSetupError("sdk", "Missing SDK") from exc
                factory = AsyncOpenAI
            client = factory(api_key=key, timeout=30, max_retries=0)
            self._status(generation, "Generating OpenAI speech…")
            stage = "speech generation/download"
            # PCM is documented as mono 24kHz signed 16-bit little-endian.
            # Finalize our own WAV header: streaming WAV length placeholders
            # can be rejected by Windows SoundPlayer during PlaySync.
            with tempfile.TemporaryDirectory(prefix="ada-speech-") as directory:
                path = Path(directory) / "response.wav"
                async with client.audio.speech.with_streaming_response.create(
                    model="gpt-4o-mini-tts", voice=voice, input=text,
                    instructions=STYLE, speed=speed, response_format="pcm",
                ) as response:
                    with wave.open(str(path), "wb") as output:
                        output.setnchannels(1)
                        output.setsampwidth(2)
                        output.setframerate(24000)
                        size = 0
                        async for chunk in response.iter_bytes():
                            if not self._current(generation):
                                return
                            size += len(chunk)
                            if size > 32 * 1024 * 1024:
                                raise ValueError("Audio response too large")
                            output.writeframesraw(chunk)
                        if size == 0 or size % 2:
                            raise ValueError("Incomplete PCM response")
                if self._current(generation):
                    stage = "native audio playback"
                    self._status(generation, "Speaking with OpenAI AI-generated voice.")
                    await self._player(path)
                    self._status(generation, "OpenAI speech ready.")
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            known = (isinstance(exc, (AgentSetupError, OSError))
                     or getattr(exc, "status_code", None) is not None
                     or type(exc).__name__ in {"APIConnectionError", "APITimeoutError"})
            detail = error_message(exc) if known else "Check the audio output device or choose System (local)."
            self._status(generation, f"Speech failed during {stage}. {detail} The response remains in chat.")
        finally:
            if client is not None:
                await client.close()

    async def _play(self, path):
        command = playback_command(path)
        if not command:
            raise RuntimeError("No audio player")
        environment = dict(os.environ)
        environment.pop("OPENAI_API_KEY", None)
        environment["ADA_SPEECH_WAV"] = str(path)
        options = {"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}
        process = None
        # Shield process creation so cancellation cannot orphan the audio helper.
        launch = asyncio.create_task(asyncio.create_subprocess_exec(
            *command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, env=environment, **options))
        try:
            process = await asyncio.shield(launch)
            if await asyncio.wait_for(process.wait(), timeout=120):
                raise RuntimeError("Audio playback failed")
        finally:
            if process is None:
                process = await launch
            if process.returncode is None:
                try:
                    process.terminate()
                except ProcessLookupError:
                    pass
                await process.wait()
