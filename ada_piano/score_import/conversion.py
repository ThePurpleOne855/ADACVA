"""Cancellable Audiveris subprocess, with retained inputs, outputs, and diagnostics."""

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
from threading import Event, Lock, Thread
from time import monotonic
from uuid import uuid4

from ada_piano.music_sheet.musicxml import _read
from .launcher import audiveris_command

DEFAULT_LIBRARY = Path(__file__).resolve().parents[2] / "scores"


def score_parts(path):
    root = _read(Path(path))
    if root.tag != "score-partwise":
        raise ValueError("Only score-partwise MusicXML is supported.")
    names = {p.get("id"): p.findtext("part-name", "Unnamed")
             for p in root.findall("./part-list/score-part")}
    parts = []
    for part in root.findall("part"):
        if not part.get("id"):
            raise ValueError("Score part is missing its ID.")
        parts.append({"id": part.get("id"), "name": names.get(part.get("id"), "Unnamed"),
                      "measures": len(part.findall("measure")),
                      "staves": sorted({n.findtext("staff", "1") for n in part.iter("note")}),
                      "voices": sorted({n.findtext("voice", "1") for n in part.iter("note")})})
    if not parts:
        raise ValueError("No parts found in MusicXML.")
    return parts


def save_json(path, data):
    path = Path(path)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    temporary.replace(path)


@dataclass(frozen=True)
class ImportStatus:
    state: str = "idle"
    detail: str = "Choose a PDF or MusicXML file."
    folder: Path | None = None
    source: Path | None = None
    outputs: tuple[Path, ...] = ()
    elapsed: float = 0


class ScoreImporter:
    def __init__(self, library=DEFAULT_LIBRARY, timeout=1800, command=None):
        self.library = Path(library)
        self.timeout = timeout
        # Command injection is a test/integration seam; GUI supplies one executable.
        self.command = tuple(command) if command is not None else None
        self._lock = Lock()
        self._cancel = Event()
        self._thread = None
        self._status = ImportStatus()

    @property
    def running(self):
        return self._thread is not None and self._thread.is_alive()

    @property
    def status(self):
        with self._lock:
            return self._status

    def _set(self, state, detail, folder=None, source=None, outputs=(), elapsed: float = 0):
        with self._lock:
            self._status = ImportStatus(state, detail, folder, source, tuple(outputs), elapsed)

    def start(self, source, executable="auto"):
        if self.running:
            raise RuntimeError("An import is running. Cancel it or wait before starting another.")
        source = Path(source).expanduser().resolve()
        if not source.is_file() or source.suffix.lower() not in {".pdf", ".musicxml", ".xml", ".mxl"}:
            raise ValueError("Choose an existing PDF, MusicXML, XML, or MXL file.")
        self._cancel.clear()
        self._set("running", "Saving a local copy…")
        # Let cancellation cleanup finish before Python exits, especially when a
        # Windows launcher still has a Java child to terminate.
        self._thread = Thread(target=self._run, args=(source, executable), daemon=False)
        self._thread.start()

    @staticmethod
    def _kill(process):
        if process.poll() is not None:
            return
        if os.name == "posix":
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        else:
            # Stop the launcher and its Java child, not only the launcher.
            try:
                subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)
            finally:
                if process.poll() is None:
                    process.kill()
        process.wait(timeout=5)

    def _run(self, source, executable):
        started = monotonic()
        folder = copied = None
        process = None
        state, detail, outputs = "error", "Import did not finish.", ()
        try:
            folder = self.library / (datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-") + uuid4().hex[:8])
            folder.mkdir(parents=True)
            copied = folder / ("source" + source.suffix.lower())
            shutil.copy2(source, copied)
            if self._cancel.is_set():
                state, detail = "cancelled", "Import cancelled. Source retained."
                return
            if copied.suffix == ".pdf":
                command = self.command
                if command is None:
                    command = audiveris_command(executable, folder)
                output = folder / "output"
                output.mkdir()
                argv = [*command, "-batch", "-transcribe", "-export", "-save", "-output", str(output.resolve()),
                        "--", str(copied.resolve())]
                save_json(folder / "command.json", argv)
                with (folder / "conversion.log").open("wb") as log:
                    process = subprocess.Popen(argv, stdout=log, stderr=subprocess.STDOUT,
                                               stdin=subprocess.DEVNULL,
                                               start_new_session=os.name == "posix")
                    while process.poll() is None:
                        elapsed = monotonic() - started
                        engine = "Audiveris (Flatpak)" if "org.audiveris.audiveris" in command else "Audiveris"
                        self._set("running", f"{engine} is converting the PDF…", folder, copied, elapsed=elapsed)
                        if self._cancel.wait(0.1):
                            self._kill(process)
                            state, detail = "cancelled", "Conversion cancelled. Source and diagnostics retained."
                            return
                        if elapsed >= self.timeout:
                            self._kill(process)
                            raise RuntimeError(f"Conversion exceeded its {self.timeout:g}-second time limit. See conversion.log.")
                    if process.returncode:
                        raise RuntimeError(f"Audiveris exited with code {process.returncode}. See conversion.log.")
                candidates = sorted(p for p in output.rglob("*") if p.suffix.lower() in {".mxl", ".musicxml", ".xml"})
                valid = []
                for path in candidates:
                    try:
                        score_parts(path)
                        valid.append(path)
                    except (ValueError, OSError) as exc:
                        with (folder / "conversion.log").open("a", encoding="utf-8") as log:
                            log.write(f"\nSkipped {path.name}: {exc}\n")
                outputs = tuple(valid)
                if not outputs:
                    raise RuntimeError("Audiveris produced no readable MusicXML. Review conversion.log and the saved OMR project.")
            else:
                score_parts(copied)
                outputs = (copied,)
            if self._cancel.is_set():
                state, detail, outputs = "cancelled", "Import cancelled. Files retained.", ()
            else:
                state, detail = "ready", "File available — needs review. Select a passage and load its preview."
        except Exception as exc:
            detail = str(exc)
        finally:
            if process is not None and process.poll() is None:
                try:
                    self._kill(process)
                except Exception as exc:
                    detail += f" Could not stop converter: {exc}"
            elapsed = monotonic() - started
            if folder is not None:
                try:
                    save_json(folder / "import.json", {
                        "state": state, "detail": detail, "original": str(source),
                        "source": str(copied), "outputs": [str(p) for p in outputs],
                        "elapsed_seconds": elapsed, "reviewed": False,
                    })
                except OSError as exc:
                    state, detail, outputs = "error", f"Could not save import record: {exc}", ()
            self._set(state, detail, folder, copied, outputs if state == "ready" else (), elapsed)

    def cancel(self):
        self._cancel.set()

    def close(self):
        self.cancel()
        if self._thread is not None:
            self._thread.join(timeout=0.3)

    def diagnostics(self):
        folder = self.status.folder
        if folder is None or not (folder / "conversion.log").exists():
            return self.status.detail
        with (folder / "conversion.log").open("rb") as log:
            log.seek(0, 2)
            log.seek(max(0, log.tell() - 32768))
            return log.read().decode("utf-8", errors="replace")
