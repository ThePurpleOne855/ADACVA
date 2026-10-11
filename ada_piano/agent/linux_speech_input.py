"""Opt-in Linux recording and cancellable cloud transcription, without Tk calls."""
import asyncio
from array import array
import importlib.util
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


VIRTUAL_SOURCE = ("aloop", ".monitor", "droidcam", "loopback", "dummy")


_chosen_target = []  # cached once per run: [name or None]


def _level(engine, target):
    """AC loudness of 0.6 s from one source; 0 for a dead/muted mic."""
    import subprocess
    try:
        data = subprocess.run([engine, "--target", target, "--raw", "--format", "s16", "--rate", str(RATE),
                               "--channels", "1", "-"], capture_output=True, timeout=0.8).stdout
    except subprocess.TimeoutExpired as exc:
        data = exc.stdout or b""
    except OSError:
        return 0
    samples = array("h", data[len(data) // 4:])  # skip the start-up click
    if not samples:
        return 0
    mean = sum(samples) / len(samples)
    return (sum((x - mean) ** 2 for x in samples) / len(samples)) ** .5


def microphone_target(engine=None, run=None, level=_level):
    """Choose a microphone that actually carries sound: the default if it works,
    otherwise the first real (non-loopback) source with signal. Cached per run."""
    import subprocess
    if _chosen_target:
        return _chosen_target[0]
    run = run or (lambda args: subprocess.run(args, capture_output=True, text=True, timeout=2).stdout)
    try:
        default = run(["pactl", "get-default-source"]).strip()
        names = [line.split("\t")[1] for line in run(["pactl", "list", "short", "sources"]).splitlines()
                 if line.count("\t") >= 2]
    except (OSError, IndexError, subprocess.SubprocessError):
        return None
    real = [n for n in names if not any(word in n.lower() for word in VIRTUAL_SOURCE)]
    candidates = ([default] if default in real else []) + [n for n in real if n != default]
    choice = next((n for n in candidates if level(engine, n) > 20), None) if engine else None
    if choice == default:
        choice = None  # keep the system default; no --target needed
    _chosen_target.append(choice)
    return choice


def recording_command():
    engine = shutil.which("pw-record")
    target = os.environ.get("ADA_MIC_TARGET") or (microphone_target(engine) if engine and shutil.which("pactl") else None)
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
        self.floor = float("inf")  # quietest level heard before speech: the room's noise

    def feed(self, frame):
        samples = array("h", frame)
        if sys.byteorder != "little":
            samples.byteswap()
        # Remove DC offset first: some USB/webcam mics sit at a constant bias that is not sound.
        mean = sum(samples) / max(1, len(samples))
        rms = (sum((x - mean) ** 2 for x in samples) / max(1, len(samples))) ** .5
        if not self.frames:
            self.floor = min(self.floor, rms)
        # Speech is clearly above the room's noise, so a loud mic or fan cannot keep it "talking".
        speech = rms >= max(250, 2.5 * self.floor)
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


HINT = "Ada, Für Elise, Ode to Joy, record, replay, play it for me, how did I do, stop, help, camera."
_local_model = None
_model_lock = Lock()


def local_available():
    return importlib.util.find_spec("faster_whisper") is not None


def transcribe_locally(wav_bytes):
    """Offline speech-to-text (faster-whisper base.en, CPU). First use downloads ~140 MB."""
    global _local_model
    import numpy as np
    with _model_lock:
        if _local_model is None:
            from faster_whisper import WhisperModel
            _local_model = WhisperModel(os.environ.get("ADA_WHISPER_MODEL", "base.en"),
                                        device="cpu", compute_type="int8")
        with wave.open(io.BytesIO(wav_bytes)) as source:
            pcm = np.frombuffer(source.readframes(source.getnframes()), dtype="<i2")
        audio = pcm.astype(np.float32) / 32768
        audio -= audio.mean()  # DC offset from some USB microphones
        segments, _ = _local_model.transcribe(audio, language="en", beam_size=1,
                                              initial_prompt=HINT, vad_filter=False)
        return " ".join(segment.text for segment in segments).strip()


class LinuxSpeechInput:
    cloud_transcription = True

    def __init__(self, *, recorder=None, client_factory=None):
        self.available = recorder is not None or recording_command() is not None
        self.status = ("Microphone off." if self.available else
                       "Install PipeWire tools or alsa-utils to record audio.")
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
            if not key and (self._client_factory is not None or not local_available()):
                self.available = False
                self.status = ("Open API settings to set a key, or install offline speech "
                               "recognition with: uv sync --extra voice")
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
                if not key:
                    self._status(generation, "Understanding what you said…")
                    text = await asyncio.to_thread(transcribe_locally, audio)
                    with self._lock:
                        if self._closed or generation != self._generation:
                            return
                        if 0 < len(text) <= 2000:
                            self._events.append(text)
                            self.status = f"Heard: {text}"
                        else:
                            self.status = "I didn't catch that. Try again a little louder."
                    if not continuous:
                        return
                    await asyncio.sleep(.15)
                    continue
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
