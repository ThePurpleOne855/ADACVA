"""Natural offline speech with Piper (neural TTS), same contract as VoiceService.

The model loads once on a background thread; each utterance is synthesized to
a temporary WAV and played by the native player, which stop() terminates.
"""
from collections import deque
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from threading import Condition, Event, Thread
import wave

DEFAULT_VOICE = "en_US-lessac-medium"


def voice_dir():
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / "ada-piano" / "voices"


def model_path():
    """ADA_PIPER_VOICE may name a model file; otherwise the downloaded default."""
    configured = os.environ.get("ADA_PIPER_VOICE")
    return Path(configured) if configured else voice_dir() / f"{DEFAULT_VOICE}.onnx"


def available():
    try:
        import piper  # noqa: F401
    except ImportError:
        return False
    return model_path().is_file()


def download(name=DEFAULT_VOICE):
    """One-time model download (about 60 MB) into the user data folder."""
    try:
        from piper.download_voices import download_voice
    except ImportError as exc:
        raise RuntimeError("Install the voice extra first: uv sync --extra voice") from exc
    folder = voice_dir()
    folder.mkdir(parents=True, exist_ok=True)
    download_voice(name, folder)
    return folder / f"{name}.onnx"


def spoken(text):
    """Read note names naturally: "F sharp4" -> "F sharp 4", "C#4" -> "C sharp 4"."""
    text = re.sub(r"\b([A-G])#", r"\1 sharp ", text)
    text = re.sub(r"\b([A-G])b(?=\d)", r"\1 flat ", text)
    text = re.sub(r"\b([A-G](?: sharp| flat)?) ?(\d)\b", r"\1 \2", text)
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    return text.replace("`", "").replace("ADA", "Ada")


class PiperVoiceService:
    def __init__(self, model=None, *, player=None, loader=None):
        from ada_piano.agent.cloud_voice import playback_command
        self._command = player or playback_command
        self._loader = loader
        self._model_path = Path(model) if model else model_path()
        self.available = self._command("probe.wav") is not None and (loader is not None or available())
        self.status = ("Natural offline voice ready." if self.available else
                       "Offline voice not installed; run: uv run ada-piano voice-setup")
        self._voice = None
        self._condition = Condition()
        self._queue = deque()
        self._process = None
        self._closed = False
        self._generation = 0
        self._thread = Thread(target=self._run, name="ada-piper-voice", daemon=True)
        self._thread.start()

    def say(self, text, *, replace=True):
        done = Event()
        with self._condition:
            if self._closed or not self.available or not text.strip():
                done.set()
                return done
            if replace:
                self._cancel_locked()
            self._queue.append((spoken(text), done, self._generation))
            self._condition.notify()
        return done

    def _cancel_locked(self):
        self._generation += 1
        while self._queue:
            self._queue.popleft()[1].set()
        if self._process is not None:
            try:
                self._process.terminate()
            except OSError:
                pass

    def stop(self):
        with self._condition:
            self._cancel_locked()
            self._condition.notify()

    def close(self):
        with self._condition:
            self._closed = True
            self._cancel_locked()
            self._condition.notify()
        self._thread.join(timeout=1)

    def _load(self):
        if self._voice is None:
            if self._loader is not None:
                self._voice = self._loader(self._model_path)
            else:
                from piper import PiperVoice
                self._voice = PiperVoice.load(str(self._model_path))
        return self._voice

    def _run(self):
        if self.available:
            try:
                self._load()  # warm up so the first sentence is not delayed
            except Exception:
                self.available = False
                self.status = "Offline voice failed to load; continuing in text mode."
        with tempfile.TemporaryDirectory(prefix="ada-voice-") as directory:
            path = Path(directory) / "speech.wav"
            while True:
                with self._condition:
                    self._condition.wait_for(lambda: self._closed or self._queue)
                    if self._closed:
                        return
                    text, done, generation = self._queue.popleft()
                try:
                    with wave.open(str(path), "wb") as output:
                        self._load().synthesize_wav(text, output)
                    with self._condition:
                        if generation != self._generation or self._closed:
                            continue
                        options = {"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}
                        env = {**os.environ, "ADA_SPEECH_WAV": str(path)}
                        self._process = subprocess.Popen(self._command(path), stdout=subprocess.DEVNULL,
                                                         stderr=subprocess.DEVNULL, env=env, **options)
                    self._process.wait(timeout=120)
                except Exception:
                    self.status = "Offline speech failed for one message; text is still shown."
                finally:
                    with self._condition:
                        if self._process is not None and self._process.poll() is None:
                            self._process.kill()
                        self._process = None
                    done.set()
