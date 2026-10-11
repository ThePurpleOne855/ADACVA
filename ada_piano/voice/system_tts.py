"""Cancellable subprocess speech with one replaceable queued utterance."""
from collections import deque
import shutil
import subprocess
import sys
from threading import Condition, Event, Thread


def system_command():
    if sys.platform == "darwin":
        engine = shutil.which("say")
        return [engine] if engine else None
    if sys.platform == "win32":
        engine = shutil.which("powershell.exe")
        script = ("[Console]::InputEncoding = [System.Text.Encoding]::UTF8; "
                  "Add-Type -AssemblyName System.Speech; "
                  "$speaker = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
                  "$speaker.Speak([Console]::In.ReadToEnd()); $speaker.Dispose()")
        return [engine, "-NoProfile", "-NonInteractive", "-Command", script] if engine else None
    engine = shutil.which("espeak-ng")
    return [engine, "--stdin"] if engine else None


class VoiceService:
    def __init__(self, command=None, popen=subprocess.Popen):
        self.command = system_command() if command is None else command
        self.available = bool(self.command)
        self.status = "Speech ready." if self.available else "Speech unavailable; continuing in text mode."
        self._popen = popen
        self._condition = Condition()
        self._queue = deque()
        self._process = None
        self._closed = False
        self._generation = 0
        self._thread = Thread(target=self._run, name="ada-voice", daemon=True)
        self._thread.start()

    def say(self, text, *, replace=True):
        done = Event()
        with self._condition:
            if self._closed or not self.available:
                done.set()
                return done
            if replace:
                self._cancel_locked()
            self._queue.append((text, done, self._generation))
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

    def _run(self):
        while True:
            with self._condition:
                self._condition.wait_for(lambda: self._closed or self._queue)
                if self._closed:
                    return
                text, done, generation = self._queue.popleft()
            process = None
            try:
                with self._condition:
                    if generation != self._generation or self._closed:
                        continue
                    options = {"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}
                    process = self._popen(self.command, stdin=subprocess.PIPE,
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **options)
                    self._process = process
                process.communicate(input=text.encode("utf-8"), timeout=60)
                if process.returncode and generation == self._generation:
                    raise RuntimeError("System speech failed.")
            except Exception:
                if process is not None:
                    try:
                        process.kill()
                        process.communicate(timeout=1)
                    except Exception:
                        pass
                self.available = False
                self.status = "Speech unavailable; continuing in text mode."
            finally:
                with self._condition:
                    self._process = None
                done.set()
