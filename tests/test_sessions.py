"""Local session writes are atomic and independent of mutable UI state."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from uuid import uuid4

from ada_piano.sessions import SessionStore, save_session


class SessionTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.snapshot = {"schema_version": 1, "mode": "guided", "session_id": str(uuid4()),
                         "feedback": ["Try measure two."], "hand_analysis": None}

    def test_save_replaces_only_same_session_and_round_trips(self):
        path = save_session(self.snapshot, self.directory)
        self.assertEqual(json.loads(path.read_text()), self.snapshot)
        self.snapshot["feedback"].append("Now try three.")
        self.assertEqual(save_session(self.snapshot, self.directory), path)
        self.assertEqual(len(list(self.directory.iterdir())), 1)
        self.assertEqual(json.loads(path.read_text())["feedback"], self.snapshot["feedback"])

    def test_failed_replace_preserves_previous_file_and_cleans_temporary(self):
        path = save_session(self.snapshot, self.directory)
        previous = path.read_bytes()
        self.snapshot["feedback"].append("New feedback")
        with patch.object(Path, "replace", side_effect=OSError("disk full")), self.assertRaises(OSError):
            save_session(self.snapshot, self.directory)
        self.assertEqual(path.read_bytes(), previous)
        self.assertEqual(list(self.directory.iterdir()), [path])

    def test_invalid_format_path_and_nonfinite_values_are_rejected(self):
        for change in ({"schema_version": 2}, {"mode": "unknown"}, {"session_id": "../elsewhere"},
                       {"time": float("nan")}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                save_session({**self.snapshot, **change}, self.directory)
        self.assertEqual(list(self.directory.iterdir()), [])

    def test_background_save_copies_snapshot_and_returns_path(self):
        store = SessionStore(self.directory)
        self.addCleanup(store.close)
        store.save(self.snapshot, announce=True)
        self.snapshot["feedback"].clear()
        [(path, error, announce)] = store.flush()
        self.assertIsNone(error)
        self.assertTrue(announce)
        self.assertEqual(json.loads(Path(path).read_text())["feedback"], ["Try measure two."])

    def test_worker_failure_is_reported_without_raw_exception(self):
        store = SessionStore(self.directory)
        self.addCleanup(store.close)
        with patch("ada_piano.sessions.save_session", side_effect=OSError("private path")):
            store.save(self.snapshot)
            [(path, error, announce)] = store.flush()
        self.assertIsNone(path)
        self.assertTrue(announce)
        self.assertIn("Could not save", error)
        self.assertNotIn("private", error)
