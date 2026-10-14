"""Conservative fingertip proximity evidence joined to MIDI acquisition times.

Calibration uses one known hand's index finger and actual MIDI pitches. Camera
coordinates never establish a key press, correct fingering, or healthy posture.
All methods run on the caller's thread; no image data is retained or exported.
"""

from collections import Counter, deque
from dataclasses import dataclass
from math import hypot, isfinite
from statistics import median

from ada_piano.music_sheet import note_name


INFERENCE_DELAY = 0.18
FRAME_WINDOW = 0.10
MAX_ATTACKS = 1200
MAX_OBSERVATIONS = 24
WHITE_CLASSES = (0, 2, 4, 5, 7, 9, 11)
FINGERS = ((4, "thumb"), (8, "index"), (12, "middle"), (16, "ring"), (20, "little"))
LIMITATIONS = (
    "Camera observations show a fingertip near a calibrated MIDI key; they do not prove which "
    "finger pressed it or judge fingering, posture, or technique. MIDI establishes presses. "
    "Only the calibrated ranges and contact lines are covered. Keep the camera and piano "
    "fixed and recalibrate after either moves. Camera timestamps are host acquisition times; "
    "camera buffering or network delay is not measured. Occlusion, motion, uncertain hand "
    "labels, and ambiguous fingers produce unknown observations."
)


def _coordinate(pitch):
    octave, chroma = divmod(pitch, 12)
    if chroma in WHITE_CLASSES:
        return octave * 7 + WHITE_CLASSES.index(chroma)
    return octave * 7 + sum(key < chroma for key in WHITE_CLASSES) - 0.5


def _valid_time(timestamp):
    return type(timestamp) in (int, float) and isfinite(timestamp) and timestamp >= 0


@dataclass(frozen=True)
class _Frame:
    timestamp: float
    hands: tuple
    labels: tuple
    error: str | None = None


@dataclass
class _Attack:
    pitch: int
    timestamp: float
    calibration: bool = False
    error: str | None = None


@dataclass(frozen=True)
class _Row:
    origin: tuple[float, float]
    step: tuple[float, float]
    low: int
    high: int
    anchors: int

    @property
    def width(self):
        return hypot(*self.step)

    def position(self, pitch):
        key = _coordinate(pitch)
        return tuple(self.origin[i] + key * self.step[i] for i in (0, 1))


class HandAnalysis:
    """A bounded, optional camera observer; unavailable evidence is explicit."""

    def __init__(self):
        self._frames = deque(maxlen=180)
        self._pending = deque()
        self._held = set()
        self._rows = {}
        self._anchors = {"white": {}, "black": {}}
        self._hand = "right"
        self._label = None
        self._take_started = None
        self._take_active = False
        self._attacks = 0
        self._ignored = 0
        self._associated = 0
        self._unknown = Counter()
        self._observations = []
        self._invalidations = []
        self._last_midi = None
        self.calibrating = False
        self.status = "Hand analysis needs camera calibration. MIDI works independently."

    @property
    def calibrated(self):
        return "white" in self._rows

    def reset(self, reason="Camera changed."):
        """Invalidate geometry without erasing evidence from an ongoing take."""
        for attack in self._pending:
            if not attack.calibration:
                self._record(attack, reason="calibration_reset")
        self._pending.clear()
        self._frames.clear()
        self._held.clear()
        self._rows.clear()
        self._anchors = {"white": {}, "black": {}}
        self._label = None
        self._last_midi = None
        self.calibrating = False
        if self._take_active and len(self._invalidations) < 4:
            self._invalidations.append(str(reason)[:160])
        self.status = str(reason) + " Recalibrate hand analysis before using camera observations."
        return self.status

    def begin_calibration(self, hand="right"):
        if hand not in {"left", "right"}:
            raise ValueError("Calibration hand must be left or right.")
        if self._take_active:
            return "Stop the current practice take before calibrating your hands."
        self.reset("Starting calibration.")
        self._hand = hand
        self.calibrating = True
        self.status = (f"Keep only your {hand} hand visible. Use its index finger to press three "
                       "separated white keys across at least one octave. Press near the front of "
                       "each key, hold still for half a second, and release before the next key. "
                       "I will name each key when captured. Keep the camera and piano fixed.")
        return self.status

    def cancel_calibration(self):
        self.reset("Calibration cancelled.")
        return self.status

    def finish_calibration(self):
        if not self.calibrated:
            self.status = ("Calibration needs three separated white keys spanning at least an octave. "
                           "Use one visible hand's index finger and hold each key still for half a second.")
        else:
            self.calibrating = False
            self._pending = deque(a for a in self._pending if not a.calibration)
            colors = "White and black" if "black" in self._rows else "White"
            self.status = f"{colors} key calibration complete. "
            if "black" not in self._rows:
                self.status += "Black key observations will be unknown. "
            self.status += "Keep the camera and piano fixed. Say start practice when ready."
        return self.status

    def add_frame(self, frame):
        timestamp = getattr(frame, "captured_at_ns", None)
        if type(timestamp) is not int or timestamp < 0:
            return
        timestamp /= 1_000_000_000
        if self._frames and timestamp <= self._frames[-1].timestamp:
            return
        hands = getattr(frame, "hand_landmarks", ())
        labels = getattr(frame, "handedness", ())
        try:
            if len(hands) > 2 or len(hands) != frame.hands:
                raise ValueError
            copied = tuple(tuple((p.x, p.y) for p in hand) for hand in hands)
            if any(len(hand) != 21 for hand in hands) or any(
                    not all(type(v) in (int, float) and isfinite(v) for v in (p.x, p.y, p.z))
                    or not 0 <= p.x <= 1 or not 0 <= p.y <= 1 for hand in hands for p in hand):
                raise ValueError
            labels = tuple(labels[i] if i < len(labels) and labels[i] in {"left", "right"}
                           else None for i in range(len(hands)))
            self._frames.append(_Frame(timestamp, copied, labels))
        except (AttributeError, TypeError, ValueError):
            self._frames.append(_Frame(timestamp, (), (), "invalid_landmarks"))

    def observe(self, kind, pitch, velocity, channel, timestamp):
        if (kind not in {"on", "off"} or type(pitch) is not int or not 0 <= pitch <= 127
                or type(velocity) is not int or not 0 <= velocity <= 127
                or type(channel) is not int or not 1 <= channel <= 16 or not _valid_time(timestamp)):
            raise ValueError("Invalid MIDI observation for hand analysis.")
        if self._last_midi is not None and timestamp < self._last_midi:
            raise ValueError("MIDI timestamps must be monotonic.")
        self._last_midi = timestamp
        key = (channel, pitch)
        if kind == "off" or velocity == 0:
            self._held.discard(key)
            return
        error = "release_previous_key" if self._held else None
        self._held.add(key)
        if self.calibrating:
            for attack in self._pending:
                if attack.calibration and timestamp - attack.timestamp <= 0.06:
                    attack.error = "calibration_chord"
                    error = "calibration_chord"
            self._pending.append(_Attack(pitch, timestamp, True, error))
        elif self._take_active and timestamp >= self._take_started:
            if self._attacks < MAX_ATTACKS:
                self._attacks += 1
                self._pending.append(_Attack(pitch, timestamp))
            else:
                self._ignored += 1

    def tick(self, now):
        if not _valid_time(now):
            raise ValueError("Invalid hand analysis clock.")
        announcements = []
        while self._pending and now - self._pending[0].timestamp >= INFERENCE_DELAY:
            attack = self._pending.popleft()
            samples, reason = self._nearby(attack.timestamp)
            if attack.calibration:
                message = self._calibrate(attack, samples, attack.error or reason)
                self.status = message
                announcements.append(message)
            else:
                self._associate(attack, samples, reason)
        return announcements

    def _nearby(self, timestamp):
        samples = [f for f in self._frames if abs(f.timestamp - timestamp) <= FRAME_WINDOW]
        if not samples:
            return [], "stale_or_missing_camera"
        if any(f.error for f in samples):
            return [], "invalid_landmarks"
        if any(not f.hands for f in samples):
            return [], "no_hands"
        if (len(samples) < 2 or samples[0].timestamp > timestamp or samples[-1].timestamp < timestamp
                or samples[-1].timestamp - samples[0].timestamp < 0.02):
            return [], "insufficient_frames"
        return samples, None

    def _calibrate(self, attack, samples, reason):
        prompts = {
            "calibration_chord": "Press one calibration key at a time.",
            "release_previous_key": "Release all keys before the next calibration key.",
            "no_hands": "No hand is visible. Place your hand under the camera and try again.",
            "stale_or_missing_camera": "No recent camera frames. Check the camera and try again.",
            "invalid_landmarks": "Hand tracking was incomplete. Keep one whole hand visible and try again.",
            "insufficient_frames": "Hold your index finger still on the key for half a second and try again.",
        }
        if reason:
            return prompts[reason]
        if any(len(f.hands) != 1 for f in samples):
            return f"Keep only your {self._hand} hand visible during calibration and try again."
        labels = {f.labels[0] for f in samples}
        if None in labels:
            return "I cannot identify the hand reliably. Keep your whole hand visible and try again."
        if len(labels) != 1 or (self._label is not None and labels != {self._label}):
            return f"Hand identity changed. Keep only your {self._hand} hand visible and try again."
        points = [f.hands[0][8] for f in samples]
        center = (median(p[0] for p in points), median(p[1] for p in points))
        width = self._rows["white"].width if self.calibrated else 0.035
        if max(hypot(p[0] - center[0], p[1] - center[1]) for p in points) > min(0.008, width * 0.23):
            return "Your index finger moved during capture. Hold it still on one key and try again."
        color = "white" if attack.pitch % 12 in WHITE_CLASSES else "black"
        if color == "black" and not self.calibrated:
            return "Start with three separated white keys across at least an octave."
        anchors = self._anchors[color]
        if attack.pitch in anchors:
            return f"{note_name(attack.pitch)} is already captured. Choose a different {color} key."
        if any(abs(_coordinate(attack.pitch) - _coordinate(pitch)) < 2 for pitch in anchors):
            return f"Choose a {color} key farther from the previous keys, then hold it still."
        if len(anchors) >= 12:
            return "Calibration has too many anchors. Say calibrate hands to start again."
        anchors[attack.pitch] = center
        self._label = next(iter(labels))
        needed = 3 if color == "white" else 2
        span = _coordinate(max(anchors)) - _coordinate(min(anchors))
        if len(anchors) < needed or span < (7 if color == "white" else 4):
            return (f"Captured {note_name(attack.pitch)}. {len(anchors)} {color} keys captured. "
                    f"Press another separated {color} key farther along the keyboard.")
        row = self._fit(anchors)
        if row is None or (color == "black" and not self._parallel(row, self._rows["white"])):
            del anchors[attack.pitch]
            return (f"The position of {note_name(attack.pitch)} does not fit the keyboard. "
                    f"Keep the camera fixed and press that key again with your {self._hand} index finger.")
        self._rows[color] = row
        if color == "black":
            return f"Captured {note_name(attack.pitch)}. " + self.finish_calibration()
        return (f"Captured {note_name(attack.pitch)}. White key calibration ready from "
                f"{note_name(row.low)} to {note_name(row.high)}. Now press two separated black keys "
                "across the same area, at least seven semitones apart, with the same index finger. "
                "Hold still for half a second and release each key. Say finish calibration to use only white keys.")

    @staticmethod
    def _fit(anchors):
        points = [(_coordinate(pitch), xy) for pitch, xy in anchors.items()]
        mean_key = sum(k for k, _ in points) / len(points)
        mean = tuple(sum(p[i] for _, p in points) / len(points) for i in (0, 1))
        variance = sum((key - mean_key) ** 2 for key, _ in points)
        if variance <= 0:
            return None
        step = tuple(sum((key - mean_key) * (point[i] - mean[i]) for key, point in points) / variance
                     for i in (0, 1))
        origin = tuple(mean[i] - mean_key * step[i] for i in (0, 1))
        row = _Row(origin, step, min(anchors), max(anchors), len(anchors))
        if not 0.012 <= row.width <= 0.15:
            return None
        if any(hypot(point[0] - row.position(pitch)[0], point[1] - row.position(pitch)[1]) > row.width * 0.24
               for pitch, point in anchors.items()):
            return None
        return row

    @staticmethod
    def _parallel(black, white):
        cosine = sum(a * b for a, b in zip(black.step, white.step)) / (black.width * white.width)
        return cosine >= 0.98 and 0.85 <= black.width / white.width <= 1.15

    def begin_take(self, started_at):
        if not _valid_time(started_at):
            raise ValueError("Invalid take start time.")
        if self.calibrating:
            if self.calibrated:
                self.finish_calibration()
            else:
                self.cancel_calibration()
        self._pending.clear()
        self._held.clear()
        self._last_midi = None
        self._take_started = started_at
        self._take_active = True
        self._attacks = self._associated = 0
        self._ignored = 0
        self._unknown.clear()
        self._observations.clear()
        self._invalidations.clear()

    def finish_take(self, timestamp):
        if not _valid_time(timestamp) or self._take_started is not None and timestamp < self._take_started:
            raise ValueError("Invalid take end time.")
        if self._take_active:
            self.tick(timestamp + INFERENCE_DELAY + 0.001)
            self._take_active = False
        return self.summary()

    def _associate(self, attack, samples, reason):
        if not self.calibrated:
            self._record(attack, reason="uncalibrated")
            return
        color = "white" if attack.pitch % 12 in WHITE_CLASSES else "black"
        row = self._rows.get(color)
        if row is None:
            self._record(attack, reason="black_keys_uncalibrated")
            return
        if not row.low <= attack.pitch <= row.high:
            self._record(attack, reason="outside_calibrated_range")
            return
        if reason:
            self._record(attack, reason=reason)
            return
        if self._label is None:
            self._record(attack, reason="unknown_handedness")
            return
        candidates = []
        for frame in samples:
            if None in frame.labels or len(set(frame.labels)) != len(frame.labels):
                self._record(attack, reason="ambiguous_handedness")
                return
            nearby = []
            target = row.position(attack.pitch)
            for hand, label in zip(frame.hands, frame.labels):
                for number, (index, name) in enumerate(FINGERS, 1):
                    dx, dy = hand[index][0] - target[0], hand[index][1] - target[1]
                    along = (dx * row.step[0] + dy * row.step[1]) / row.width ** 2
                    across = (dx * row.step[1] - dy * row.step[0]) / row.width ** 2
                    if abs(along) <= 0.48 and abs(across) <= 0.8:
                        actual = self._hand if label == self._label else ("left" if self._hand == "right" else "right")
                        nearby.append((actual, number, name, hand[index], abs(along) <= 0.28 and abs(across) <= 0.55))
            if len(nearby) != 1:
                self._record(attack, reason="ambiguous_fingers" if nearby else "no_finger_near_key")
                return
            if not nearby[0][4]:
                self._record(attack, reason="finger_outside_contact_line")
                return
            candidates.append(nearby[0])
        first = candidates[0]
        if any(candidate[:2] != first[:2] for candidate in candidates):
            self._record(attack, reason="unstable_finger_identity")
            return
        if any(hypot(candidate[3][0] - first[3][0], candidate[3][1] - first[3][1]) > row.width * 0.3
               for candidate in candidates):
            self._record(attack, reason="moving_finger")
            return
        nearest = min(samples, key=lambda f: abs(f.timestamp - attack.timestamp))
        self._record(attack, observation={"hand": first[0], "finger": first[1], "finger_name": first[2],
                     "camera_offset_ms": round(1000 * (nearest.timestamp - attack.timestamp)),
                     "evidence": "fingertip_near_calibrated_midi_key"})

    def _record(self, attack, *, reason=None, observation=None):
        if reason:
            self._unknown[reason] += 1
        else:
            self._associated += 1
            if len(self._observations) < MAX_OBSERVATIONS:
                self._observations.append({"pitch": attack.pitch, "note": note_name(attack.pitch),
                    "time_seconds": round(attack.timestamp - self._take_started, 3), **observation})

    def summary(self):
        calibration = {color: {"first_midi": row.low, "last_midi": row.high,
            "first_note": note_name(row.low), "last_note": note_name(row.high), "anchors": row.anchors}
            for color, row in self._rows.items()}
        return {"kind": "calibrated_hand_midi", "calibrated": self.calibrated,
            "calibration": {"rows": calibration, "hand": self._hand,
                            "handedness_resolved": self._label is not None, "in_progress": self.calibrating},
            "midi_attacks": self._attacks, "ignored_attacks": self._ignored, "associated": self._associated,
            "unknown": sum(self._unknown.values()), "pending": sum(not a.calibration for a in self._pending),
            "coverage_percent": round(100 * self._associated / self._attacks) if self._attacks else 0,
            "unknown_reasons": dict(self._unknown), "observations": [dict(o) for o in self._observations],
            "observation_limit": MAX_OBSERVATIONS, "attack_limit": MAX_ATTACKS,
            "calibration_invalidations": list(self._invalidations), "limitations": LIMITATIONS}


def describe(summary):
    if not summary["midi_attacks"]:
        return "No MIDI notes recorded for hand analysis."
    if summary["associated"]:
        return (f"Camera evidence linked a nearby fingertip to {summary['associated']} of "
                f"{summary['midi_attacks']} MIDI notes. {summary['unknown']} were unknown. "
                "These observations do not judge correct fingering or technique." +
                (f" Analysis stopped after {summary['attack_limit']} attacks; choose a shorter take."
                 if summary.get("ignored_attacks") else ""))
    if not summary["calibrated"]:
        return "Hand observations are unavailable. Say calibrate hands to link the camera to your piano."
    return "No reliable finger associations in this take. Keep your hands visible within the calibrated area."
