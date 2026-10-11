"""Optional local Windows dictation, isolated from Tk and cloud credentials."""
import json
import math
import re
import shutil
import subprocess
import sys
from collections import deque
from threading import Lock, Thread


SCRIPT = r"""
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
$recognizer = $null
try {
    Add-Type -AssemblyName System.Speech
    $installed = [System.Speech.Recognition.SpeechRecognitionEngine]::InstalledRecognizers()
    $english = $installed | Where-Object { $_.Culture.Name -like 'en-*' } | Select-Object -First 1
    if ($null -eq $english) { throw 'Recognizer unavailable' }
    $recognizer = New-Object System.Speech.Recognition.SpeechRecognitionEngine($english.Id)
    $recognizer.LoadGrammar((New-Object System.Speech.Recognition.DictationGrammar))
    $recognizer.SetInputToDefaultAudioDevice()
    [Console]::WriteLine('{"kind":"ready"}')
    do {
        $result = $recognizer.Recognize([TimeSpan]::FromSeconds(12))
        if ($null -ne $result) {
            $data = @{kind='text'; text=$result.Text; confidence=[double]$result.Confidence}
            [Console]::WriteLine(($data | ConvertTo-Json -Compress))
        } else {
            [Console]::WriteLine('{"kind":"silence"}')
        }
    } while ($env:ADA_MIC_CONTINUOUS -eq '1')
} catch {
    [Console]::WriteLine('{"kind":"error"}')
    exit 1
} finally {
    if ($null -ne $recognizer) { $recognizer.Dispose() }
}
"""


def voice_command(text):
    """Return a wake-prefixed question or Stop, ignoring ordinary conversation."""
    match = re.match(r"^\s*(?:hey\s+)?(?:ada|aida|a\s+da)\b[\s,:.!-]*(.*)$", text, re.I)
    if not match:
        return None
    question = match.group(1).strip()
    if not question:
        return None
    if question.lower().rstrip(".!?") in {"stop", "stop practice", "stop listening"}:
        return ("stop", "")
    return ("ask", question)


class SpeechInput:
    def __init__(self, *, command=None, popen=subprocess.Popen):
        engine = shutil.which("powershell.exe") if sys.platform == "win32" else None
        self.command = command if command is not None else (
            [engine, "-NoProfile", "-NonInteractive", "-Command", SCRIPT] if engine else [])
        self.available = bool(self.command)
        self.status = "Microphone off." if self.available else "Local microphone recognition requires Windows with an English speech recognizer. Type your message instead."
        self._popen = popen
        self._lock = Lock()
        self._process = None
        self._thread = None
        self._generation = 0
        self._closed = False
        self._events = deque(maxlen=8)

    @property
    def running(self):
        return self._thread is not None and self._thread.is_alive()

    def start(self, *, continuous=False, retry=False):
        if retry:
            self.available = bool(self.command)
        if self._closed or not self.available or self.running:
            return False
        with self._lock:
            self._generation += 1
            generation = self._generation
            self._events.clear()
            self.status = "Starting microphone…"
        self._thread = Thread(target=self._run, args=(generation, continuous), name="ada-microphone", daemon=True)
        self._thread.start()
        return True

    def stop(self):
        with self._lock:
            self._generation += 1
            self._events.clear()
            process = self._process
            self.status = "Microphone off."
        if process is not None:
            try:
                process.terminate()
            except OSError:
                pass

    def close(self):
        self._closed = True
        self.stop()
        if self._thread is not None:
            self._thread.join(timeout=1)

    def drain(self):
        with self._lock:
            events = list(self._events)
            self._events.clear()
            return events

    def _run(self, generation, continuous):
        import os
        process = None
        try:
            environment = dict(os.environ)
            # The microphone helper never needs API credentials.
            environment.pop("OPENAI_API_KEY", None)
            environment["ADA_MIC_CONTINUOUS"] = "1" if continuous else "0"
            options = {"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}
            with self._lock:
                if generation != self._generation or self._closed:
                    return
                process = self._popen(self.command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                      stderr=subprocess.DEVNULL, env=environment, **options)
                self._process = process
            while True:
                line = process.stdout.readline(8193)
                if not line:
                    break
                if len(line) > 8192:
                    raise ValueError("Unexpected recognition output")
                event = json.loads(line)
                kind = event.get("kind")
                with self._lock:
                    if generation != self._generation or self._closed:
                        return
                    if kind == "ready":
                        self.status = 'Listening: say "ADA" followed by your question.' if continuous else "Listening for one question…"
                    elif kind == "text":
                        text, confidence = event.get("text"), event.get("confidence")
                        if (isinstance(text, str) and 0 < len(text.strip()) <= 2000
                                and type(confidence) in (int, float) and math.isfinite(confidence)
                                and .55 <= confidence <= 1):
                            self._events.append(text.strip())
                            self.status = "Heard speech." if continuous else "Check the recognized message, then press Ask ADA."
                        else:
                            self.status = "Speech unclear. Try again or type your message."
                    elif kind == "silence":
                        self.status = "No speech heard. Try again or check your default microphone."
                    elif kind == "error":
                        raise RuntimeError("Recognition unavailable")
            if process.wait(timeout=2):
                raise RuntimeError("Recognition unavailable")
        except Exception:
            with self._lock:
                if generation == self._generation and not self._closed:
                    self.available = False
                    self.status = "Microphone unavailable. Check Windows microphone permissions, the default recording device and English speech recognition. Type your message instead."
        finally:
            if process is not None:
                if process.poll() is None:
                    try:
                        process.kill()
                    except OSError:
                        pass
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    pass
                process.stdout.close()
            with self._lock:
                if self._process is process:
                    self._process = None
