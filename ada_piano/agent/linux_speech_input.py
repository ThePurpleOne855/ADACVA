"""Opt-in Linux recording and cancellable cloud transcription, without Tk calls."""
import asyncio
from array import array
from collections import deque
import io
import os
import shutil
import sys
from threading import Lock, Thread
import wave

from .coach import AgentSetupError, error_message


RATE = 16000
FRAME_BYTES = 3200  # 100 ms of mono signed 16-bit PCM.


def recording_command():
    engine = shutil.which("pw-record")
    target = os.environ.get("ADA_MIC_TARGET")
    if engine:
        return [engine, "--raw", "--format", "s16", "--rate", str(RATE),
                "--channels", "1", *(["--target", target] if target else []), "-"]
    engine = shutil.which("arecord")
    if engine:
        return [engine, "-q", "-D", os.environ.get("ADA_ALSA_DEVICE", "default"),
                "-t", "raw", "-f", "S16_LE", "-r", str(RATE), "-c", "1"]
    return None


class Utterance:
    """Bounded energy gate: retain pre-roll, stop after one second of silence."""
    def __init__(self):
        self.pre_roll = deque(maxlen=3)
        self.frames = []
        self.voiced = 0
        self.silent = 0

    def feed(self, frame):
        samples = array("h", frame)
        if sys.byteorder != "little":
            samples.byteswap()
        rms = (sum(x * x for x in samples) / max(1, len(samples))) ** .5
        speech = rms >= 250
        if not self.frames:
            self.pre_roll.append(frame)
            if not speech:
                return False
            self.frames.extend(self.pre_roll)
        else:
            self.frames.append(frame)
        if speech:
            self.voiced += 1
            self.silent = 0
        else:
            self.silent += 1
        return self.silent >= 10

    def wav(self):
        if self.voiced < 3:
            return None  # Ignore silence and short clicks; never upload them.
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as output:
            output.setnchannels(1)
            output.setsampwidth(2)
            output.setframerate(RATE)
            output.writeframes(b"".join(self.frames))
        return buffer.getvalue()


class LinuxSpeechInput:
    cloud_transcription = True

    def __init__(self, *, recorder=None, client_factory=None):
        self.available = recorder is not None or recording_command() is not None
        self.status = ("Microphone off. Enable listening to transcribe with OpenAI."
                       if self.available else "Install PipeWire tools or alsa-utils to record audio.")
        self._recorder = recorder or self._record
        self._custom_recorder = recorder is not None
        self._client_factory = client_factory
        self._api_key = None
        self._events = deque(maxlen=8)
        self._lock = Lock()
        self._future = None
        self._generation = 0
        self._closed = False
        self._loop = asyncio.new_event_loop()
        self._capture_lock = asyncio.Lock()
        self._thread = Thread(target=self._run_loop, name="ada-linux-microphone", daemon=True)
        self._thread.start()

    def _run_loop(self):
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_forever()
        finally:
            tasks = asyncio.all_tasks(self._loop)
            for task in tasks:
                task.cancel()
            self._loop.run_until_complete(asyncio.gather(*tasks, return_exceptions=True))
            self._loop.close()

    @property
    def running(self):
        with self._lock:
            return self._future is not None and not self._future.done()

    def configure(self, *, api_key=None):
        self.stop()
        with self._lock:
            self._api_key = api_key
            self.available = self._custom_recorder or recording_command() is not None

    def start(self, *, continuous=False, retry=False):
        with self._lock:
            if self._closed or (self._future is not None and not self._future.done()):
                return False
            if retry:
                self.available = self._custom_recorder or recording_command() is not None
            if not self.available:
                return False
            key = self._api_key or os.environ.get("OPENAI_API_KEY")
            if not key:
                self.available = False
                self.status = "Open API settings to set a key before using Linux voice input."
                return False
            self._generation += 1
            generation = self._generation
            self._events.clear()
            self.status = "Starting microphone…"
            self._future = asyncio.run_coroutine_threadsafe(
                self._listen(generation, key, continuous), self._loop)
            return True

    def _current(self, generation):
        with self._lock:
            return not self._closed and generation == self._generation

    def _status(self, generation, text):
        with self._lock:
            if not self._closed and generation == self._generation:
                self.status = text

    def stop(self):
        with self._lock:
            self._generation += 1
            self._events.clear()
            if self._future is not None:
                self._future.cancel()
            self.status = "Microphone off."

    def close(self):
        self.stop()
        with self._lock:
            if self._closed:
                return
            self._closed = True
            self._api_key = None
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join(timeout=3)

    def drain(self):
        with self._lock:
            result = list(self._events)
            self._events.clear()
            return result

    async def _record(self):
        async with self._capture_lock:
            return await self._capture()

    async def _capture(self):
        command = recording_command()
        if not command:
            raise RuntimeError("No recording tool")
        environment = dict(os.environ)
        environment.pop("OPENAI_API_KEY", None)
        process = None
        launch = asyncio.create_task(asyncio.create_subprocess_exec(
            *command, stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL, env=environment))
        try:
            process = await asyncio.shield(launch)
            utterance = Utterance()
            # Wall-clock bound also covers a disconnected / stalled audio server.
            async with asyncio.timeout(15):
                for _ in range(120):
                    frame = await process.stdout.readexactly(FRAME_BYTES)
                    if utterance.feed(frame):
                        break
            return utterance.wav()
        finally:
            if process is None:
                process = await launch
            if process.returncode is None:
                try:
                    process.terminate()
                except ProcessLookupError:
                    pass
                try:
                    await asyncio.wait_for(process.wait(), 1)
                except asyncio.TimeoutError:
                    process.kill()
                    await process.wait()

    async def _listen(self, generation, key, continuous):
        client = None
        stage = "recording"
        try:
            while self._current(generation):
                stage = "recording"
                self._status(generation, 'Listening: say "ADA" and your question, then pause.'
                             if continuous else "Listening for one question; pause when finished.")
                audio = await self._recorder()
                if not self._current(generation):
                    return
                if audio is None:
                    self._status(generation, "No speech heard. Check the selected microphone and try again.")
                    if continuous:
                        continue
                    return
                stage = "transcription"
                self._status(generation, "Transcribing audio with OpenAI…")
                if client is None:
                    factory = self._client_factory
                    if factory is None:
                        try:
                            from openai import AsyncOpenAI
                        except ImportError as exc:
                            raise AgentSetupError("sdk", "Missing SDK") from exc
                        factory = AsyncOpenAI
                    client = factory(api_key=key, timeout=30, max_retries=0)
                response = await client.audio.transcriptions.create(
                    model="gpt-4o-mini-transcribe", file=("question.wav", audio, "audio/wav"),
                    language="en", response_format="json")
                text = response.text.strip()
                with self._lock:
                    if self._closed or generation != self._generation:
                        return
                    if 0 < len(text) <= 2000:
                        self._events.append(text)
                        self.status = "Heard speech." if continuous else "Check the recognized message, then press Ask ADA."
                    else:
                        self.status = "Speech unclear or too long. Try a shorter question."
                if not continuous:
                    return
                # Let the GUI consume the event before recording the next turn.
                await asyncio.sleep(.15)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            detail = ("Check your microphone and PipeWire/ALSA input settings."
                      if stage == "recording" else error_message(exc))
            with self._lock:
                if not self._closed and generation == self._generation:
                    self.available = False
                    self.status = f"Voice input failed during {stage}. {detail} Press Speak a question to retry."
        finally:
            if client is not None:
                await client.close()
