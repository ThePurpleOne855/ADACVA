"""Measured tutor observations, independent of GUI and language models."""

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class TutorResult:
    type: str
    timestamp: float
    score_event_index: int
    measure: str
    expected_pitches: tuple[int, ...]
    expected_names: tuple[str, ...]
    played_pitches: tuple[int, ...]
    played_names: tuple[str, ...]
    message: str
    complete: bool
    attack_spread_ms: float | None = None
    allowed_spread_ms: float | None = None

    def to_dict(self):
        return asdict(self)
