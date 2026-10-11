"""In-memory attempts and bounded deterministic summaries; no sensor uploads."""

from dataclasses import asdict
import json
from pathlib import Path
from time import monotonic
from uuid import uuid4


class AttemptRecorder:
    def __init__(self, context, *, started_at=None):
        if not context.get("reviewed"):
            raise ValueError("An approved passage is required.")
        self.context = {k: v for k, v in context.items() if k != "musicxml"}
        self.attempt_id = str(uuid4())
        self.started_at = monotonic() if started_at is None else started_at
        self.ended_at = None
        self.results = []
        self.feedback = []

    def record(self, result):
        if self.ended_at is not None:
            raise ValueError("Attempt already ended.")
        from math import isfinite
        if not isfinite(result.timestamp) or result.timestamp < self.started_at:
            raise ValueError("Observation precedes the attempt or has an invalid timestamp.")
        if self.results and result.timestamp < self.results[-1].timestamp:
            raise ValueError("Observation timestamps must be monotonic.")
        self.results.append(result)
        if result.complete:
            self.finish(result.timestamp)

    def finish(self, timestamp=None):
        if self.ended_at is None:
            self.ended_at = monotonic() if timestamp is None else timestamp

    def summary(self):
        correct = {r.score_event_index for r in self.results if r.type == "correct"}
        errors = [r for r in self.results if r.type not in {"correct", "exercise_complete"}]
        troubled = {r.score_event_index for r in errors}
        groups = {}
        for r in errors:
            key = (r.type, r.measure, r.expected_pitches, r.played_pitches)
            group = groups.setdefault(key, {"type": r.type, "measure": r.measure,
                "expected": list(r.expected_names), "played": list(r.played_names),
                "occurrences": 0, "event_indices": [], "eventually_corrected": True})
            group["occurrences"] += 1
            group["event_indices"].append(r.score_event_index)
            group["eventually_corrected"] &= r.score_event_index in correct
            if r.attack_spread_ms is not None:
                group["spread_ms"] = max(group.get("spread_ms", 0), r.attack_spread_ms)
                group["threshold_ms"] = r.allowed_spread_ms
        return {"attempt_id": self.attempt_id, "score_sha256": self.context["sha256"],
                "selection": self.context["selection"],
                "events_expected": len(self.context["events"]),
                "events_completed": len(correct), "correct_first_try": len(correct - troubled),
                "complete": any(r.complete for r in self.results),
                "problems": sorted(groups.values(), key=lambda p: -p["occurrences"]),
                "limitations": "Guided pitch/chord attacks only; no rhythm or calibrated fingering judgment. MIDI timestamps currently reflect GUI polling."}

    def snapshot(self):
        return {"schema_version": 1, "attempt_id": self.attempt_id,
                "score": self.context, "start_monotonic": self.started_at,
                "end_monotonic": self.ended_at, "results": [asdict(r) for r in self.results],
                "summary": self.summary(), "feedback": list(self.feedback)}

    def save(self, path):
        """Explicit export: caller must invoke outside the MIDI/UI thread."""
        Path(path).write_text(json.dumps(self.snapshot(), indent=2), encoding="utf-8")

    @staticmethod
    def load(path):
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
            if not isinstance(data, dict) or data.get("schema_version") != 1:
                raise ValueError("Unsupported attempt schema.")
            if not isinstance(data.get("results"), list) or not isinstance(data.get("summary"), dict):
                raise ValueError("Invalid attempt data.")
            if not isinstance(data.get("score"), dict) or not data["score"].get("reviewed"):
                raise ValueError("Invalid score metadata.")
            from ada_piano.ai_tutor.results import TutorResult
            import math
            for result in data["results"]:
                parsed = TutorResult(**result)
                if not math.isfinite(parsed.timestamp) or type(parsed.score_event_index) is not int:
                    raise ValueError("Invalid observation.")
            return data
        except (OSError, ValueError, TypeError) as exc:
            raise ValueError("Cannot load attempt file.") from exc
