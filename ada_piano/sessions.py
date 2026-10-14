"""Atomic local session exports, written outside the MIDI and Tk threads."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import json
import os
from pathlib import Path
from queue import Empty, Queue
import sys
import tempfile
from uuid import UUID


def sessions_dir():
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / "ada-piano" / "sessions"


def save_session(snapshot, directory):
    """Replace only this session's file; a failed write preserves the previous copy."""
    if snapshot.get("schema_version") != 1 or snapshot.get("mode") not in {"guided", "play_through"}:
        raise ValueError("Invalid session format.")
    identifier = str(UUID(snapshot["session_id"]))
    content = json.dumps(snapshot, indent=2, ensure_ascii=False, allow_nan=False)
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    destination = directory / f"{identifier}.json"
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=directory,
                                         prefix=".session-", suffix=".tmp", delete=False) as output:
            temporary = Path(output.name)
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
        temporary.replace(destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return destination


class SessionStore:
    def __init__(self, directory=None):
        self.directory = Path(directory) if directory is not None else sessions_dir()
        self._worker = ThreadPoolExecutor(max_workers=1, thread_name_prefix="ada-session-save")
        self._results = Queue()

    def save(self, snapshot, *, announce=False):
        future = self._worker.submit(save_session, deepcopy(snapshot), self.directory)
        def finished(result):
            try:
                self._results.put((str(result.result()), None, announce))
            except Exception:
                self._results.put((None, "Could not save your session. Check free disk space and folder permissions.", True))
        future.add_done_callback(finished)

    def drain(self):
        results = []
        while True:
            try:
                results.append(self._results.get_nowait())
            except Empty:
                return results

    def close(self):
        self._worker.shutdown(wait=True)

    def flush(self):
        self._worker.submit(lambda: None).result()
        return self.drain()
