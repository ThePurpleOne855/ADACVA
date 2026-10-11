"""Free play-through comparison: align recorded MIDI with an approved passage.

Unlike the guided Tutor, which waits for each correct attack, a play-through is
recorded without interruption and compared afterwards. Pitch alignment uses
edit distance, so one wrong, missed or extra note does not shift every later
comparison. Timing is measured against a tempo fitted to the correctly played
notes, so a steady but slow performance is not reported as uniformly late.
"""

from dataclasses import dataclass
from math import isfinite
from statistics import median

from ada_piano.music_sheet import Exercise, note_name

CHORD_GAP = 0.06  # seconds; overlapping attacks closer than this are ordered by pitch
MAX_EXPECTED = 2000
MAX_PLAYED = 4000
MAX_ITEMS = 5  # per measure and category, keeping the model context small
MAX_MEASURES = 16
LIMITATIONS = ("Pitch, onset timing relative to your own fitted tempo, hesitations and key-held "
               "duration only. Sustain pedal, dynamics, articulation and fingering are not judged. "
               "Held duration is key release, not audible length under the pedal.")


@dataclass(frozen=True)
class PlayedNote:
    pitch: int
    onset: float
    release: float | None = None
    velocity: int = 0


@dataclass(frozen=True)
class ExpectedNote:
    pitch: int
    beat: float
    duration: float
    measure: str
    event_index: int


class PlayThrough:
    """Collects presses/releases from one learner take; GUI-thread only."""

    def __init__(self, started_at):
        self.started_at = started_at
        self.notes: list[PlayedNote] = []
        self._open: dict[tuple[int, int], int] = {}
        self.last_activity = started_at
        self.ended_at = None

    @property
    def held(self):
        return bool(self._open)

    def observe(self, kind, pitch, velocity, channel, timestamp):
        if self.ended_at is not None or not isfinite(timestamp) or timestamp < self.started_at:
            return
        self.last_activity = max(self.last_activity, timestamp)
        key = (channel, pitch)
        if kind == "on" and velocity > 0:
            if len(self.notes) >= MAX_PLAYED:
                return
            if key in self._open:  # retrigger without release: close the previous note
                self._close(key, timestamp)
            self._open[key] = len(self.notes)
            self.notes.append(PlayedNote(pitch, timestamp, None, velocity))
        else:
            self._close(key, timestamp)

    def _close(self, key, timestamp):
        index = self._open.pop(key, None)
        if index is not None:
            note = self.notes[index]
            self.notes[index] = PlayedNote(note.pitch, note.onset, timestamp, note.velocity)

    def idle_for(self, now):
        return 0.0 if self.held or not self.notes else now - self.last_activity

    def finish(self, timestamp):
        if self.ended_at is None:
            self.ended_at = timestamp
            for key in list(self._open):
                self._close(key, timestamp)


def expected_notes(exercise: Exercise) -> list[ExpectedNote]:
    notes = []
    for index, event in enumerate(exercise.events):
        durations = {}
        for tone in event.tones:
            durations[tone.pitch] = max(durations.get(tone.pitch, 0), tone.duration)
        notes.extend(ExpectedNote(pitch, float(event.onset), float(duration), event.measure, index)
                     for pitch, duration in sorted(durations.items()))
    if len(notes) > MAX_EXPECTED:
        raise ValueError(f"Passage too long to compare (over {MAX_EXPECTED} notes). Choose fewer measures.")
    return notes


def _ordered(played):
    """Order attacks in time, but by pitch inside a near-simultaneous chord."""
    played = sorted(played, key=lambda n: n.onset)
    clusters, result = [], []
    for note in played:
        # A chord needs keys held together; quick detached notes keep their order.
        if (clusters and note.onset - clusters[-1][-1].onset <= CHORD_GAP
                and all(n.release is None or n.release > note.onset for n in clusters[-1])):
            clusters[-1].append(note)
        else:
            clusters.append([note])
    for cluster in clusters:
        result.extend(sorted(cluster, key=lambda n: (n.pitch, n.onset)))
    return result


def align(expected, played):
    """Edit-distance alignment. Returns (expected_index | None, played_index | None) pairs.

    A substitution (wrong note) costs less than a miss plus an extra. Unplayed
    expected notes after the learner stops are free: they are "not reached".
    """
    n, m = len(expected), len(played)
    if m > MAX_PLAYED:
        raise ValueError("Too many played notes to compare.")
    inf = float("inf")
    cost = [[inf] * (m + 1) for _ in range(n + 1)]
    move = [[None] * (m + 1) for _ in range(n + 1)]
    cost[0][0] = 0
    for i in range(n + 1):
        row, previous = cost[i], cost[i - 1] if i else None
        for j in range(m + 1):
            if i and j:
                step = 0 if expected[i - 1].pitch == played[j - 1].pitch else 1
                if previous[j - 1] + step < row[j]:
                    row[j], move[i][j] = previous[j - 1] + step, "pair"
            if i and previous[j] + 1 < row[j]:
                row[j], move[i][j] = previous[j] + 1, "miss"
            if j and row[j - 1] + 1 < row[j]:
                row[j], move[i][j] = row[j - 1] + 1, "extra"
    # Free trailing misses: choose the best expected prefix that consumed all playing.
    end = min(range(n + 1), key=lambda i: (cost[i][m], -i))
    pairs = [(i, None) for i in range(n - 1, end - 1, -1)]
    i, j = end, m
    while i or j:
        step = move[i][j]
        if step == "pair":
            i, j = i - 1, j - 1
            pairs.append((i, j))
        elif step == "miss":
            i -= 1
            pairs.append((i, None))
        else:
            j -= 1
            pairs.append((None, j))
    pairs.reverse()
    return pairs, end


def _fit(points):
    """Least squares time = offset + seconds_per_beat * beat, refit without outliers."""
    def solve(sample):
        if len(sample) < 2:
            return None
        mean_b = sum(b for b, _ in sample) / len(sample)
        mean_t = sum(t for _, t in sample) / len(sample)
        spread = sum((b - mean_b) ** 2 for b, _ in sample)
        if spread <= 0:
            return None
        slope = sum((b - mean_b) * (t - mean_t) for b, t in sample) / spread
        return (mean_t - slope * mean_b, slope) if slope > 0 else None

    fit = solve(points)
    if fit is None:
        return None
    residuals = [abs(t - fit[0] - fit[1] * b) for b, t in points]
    limit = max(3 * median(residuals), 0.05)
    trimmed = [p for p, r in zip(points, residuals) if r <= limit]
    return solve(trimmed) or fit


def compare(exercise: Exercise, played, *, target_bpm=None):
    expected = expected_notes(exercise)
    played = _ordered([n for n in played if 0 <= n.pitch <= 127 and isfinite(n.onset)])
    pairs, reached = align(expected, played)
    matches = [(e, p) for e, p in pairs if e is not None and p is not None
               and expected[e].pitch == played[p].pitch]
    measures = {}

    def bucket(label):
        return measures.setdefault(label, {"measure": label, "expected": 0, "correct": 0,
                                           "wrong": [], "missed": [], "extra": [], "early": [],
                                           "late": [], "short": [], "hesitations": 0})

    for note in expected[:reached]:
        bucket(note.measure)["expected"] += 1
    last_measure = expected[0].measure if expected else ""
    for e, p in pairs:
        if e is not None:
            last_measure = expected[e].measure
        if e is not None and e >= reached:
            continue
        if e is None:
            bucket(last_measure)["extra"].append(note_name(played[p].pitch))
        elif p is None:
            bucket(expected[e].measure)["missed"].append(note_name(expected[e].pitch))
        elif expected[e].pitch == played[p].pitch:
            bucket(expected[e].measure)["correct"] += 1
        else:
            bucket(expected[e].measure)["wrong"].append(
                {"expected": note_name(expected[e].pitch), "played": note_name(played[p].pitch)})

    tempo = {"target_bpm": target_bpm, "estimated_bpm": None, "typical_offset_ms": None}
    fit = _fit([(expected[e].beat, played[p].onset) for e, p in matches]) if len(matches) >= 4 else None
    if fit is not None:
        offset, spb = fit
        tempo["estimated_bpm"] = round(60 / spb)
        tolerance = max(0.12, 0.25 * spb)
        deviations = []
        for e, p in matches:
            note, attack = expected[e], played[p]
            error = attack.onset - (offset + spb * note.beat)
            deviations.append(abs(error))
            box = bucket(note.measure)
            if error < -tolerance:
                box["early"].append(note_name(note.pitch))
            elif error > tolerance:
                box["late"].append(note_name(note.pitch))
            wanted = note.duration * spb
            if attack.release is not None and wanted >= 0.4 and attack.release - attack.onset < 0.5 * wanted:
                box["short"].append(note_name(note.pitch))
        tempo["typical_offset_ms"] = round(median(deviations) * 1000)
        # A hesitation is a pause well beyond the written gap between consecutive matches.
        for (e1, p1), (e2, p2) in zip(matches, matches[1:]):
            written = (expected[e2].beat - expected[e1].beat) * spb
            actual = played[p2].onset - played[p1].onset
            if actual - written > max(0.5, spb):
                bucket(expected[e2].measure)["hesitations"] += 1

    correct = len(matches)
    totals = {k: sum(len(b[k]) for b in measures.values())
              for k in ("wrong", "missed", "extra", "early", "late", "short")}
    problems = []
    for box in measures.values():
        score = (2 * (len(box["wrong"]) + len(box["missed"])) + len(box["extra"])
                 + len(box["early"]) + len(box["late"]) + len(box["short"]) + 2 * box["hesitations"])
        if score:
            problems.append((score, box))
    problems.sort(key=lambda item: -item[0])
    detail = []
    for _, box in problems[:MAX_MEASURES]:
        item = {"measure": box["measure"], "notes_expected": box["expected"], "correct": box["correct"]}
        for key in ("wrong", "missed", "extra", "early", "late", "short"):
            if box[key]:
                item[key] = box[key][:MAX_ITEMS]
                if len(box[key]) > MAX_ITEMS:
                    item[f"{key}_total"] = len(box[key])
        if box["hesitations"]:
            item["hesitations"] = box["hesitations"]
        detail.append(item)
    reached_count = reached
    return {
        "kind": "play_through",
        "notes_expected": len(expected), "notes_reached": reached_count,
        "notes_played": len(played), "correct": correct,
        "pitch_accuracy_percent": round(100 * correct / reached_count) if reached_count else 0,
        **totals, "hesitations": sum(b["hesitations"] for b in measures.values()),
        "complete": reached_count == len(expected) and bool(expected),
        "stopped_in_measure": expected[reached - 1].measure if reached else None,
        "tempo": tempo,
        "measures_needing_work": [item["measure"] for item in detail[:3]],
        "measure_details": detail,
        "clean_measures": [label for label, box in measures.items()
                           if box["expected"] and not any(box is b for _, b in problems)],
        "limitations": LIMITATIONS,
    }


def describe(report):
    """Short spoken summary of a play-through report; usable without any cloud model."""
    reached = report["notes_reached"]
    if not report["notes_played"] or not reached:
        return "I didn't hear any notes from the piano. Check the MIDI connection and try again."
    parts = [f"{report['correct']} of {reached} notes correct"]
    if report["complete"]:
        parts[0] = "You reached the end. " + parts[0]
    else:
        parts[0] = f"You stopped in measure {report['stopped_in_measure']}. " + parts[0]
    bpm = report["tempo"]["estimated_bpm"]
    if bpm:
        target = report["tempo"]["target_bpm"]
        pace = f"about {bpm} beats per minute"
        if target and abs(bpm - target) >= max(6, 0.1 * target):
            pace += f", target {target}"
        parts.append(pace)
    sentences = [", ".join(parts) + "."]
    details = report["measure_details"]
    if not details:
        sentences.append("Clean play-through. Try a little faster, or the next passage.")
        return " ".join(sentences)
    worst = details[0]
    issues = []
    if worst.get("wrong"):
        first = worst["wrong"][0]
        issues.append(f"you played {first['played']} instead of {first['expected']}")
    if worst.get("missed"):
        issues.append("you missed " + " and ".join(worst["missed"][:2]))
    if worst.get("extra"):
        issues.append("there was an extra " + worst["extra"][0])
    if worst.get("hesitations"):
        issues.append("you paused")
    if worst.get("early") and not issues:
        issues.append("you rushed")
    if worst.get("late") and not issues:
        issues.append("some notes came late")
    if worst.get("short") and not issues:
        issues.append(worst["short"][0] + " was released too early")
    sentences.append(f"Work on measure {worst['measure']}: " + ", ".join(issues[:2]) + ".")
    return " ".join(sentences)
