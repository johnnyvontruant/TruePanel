"""
Evidence aggregation for protocol-discovery experiments.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .observation import (
    ObservationOutcome,
    ProtocolObservation,
)


class EvidenceVerdict(str, Enum):
    SUPPORTED = "supported"
    REJECTED = "rejected"
    UNKNOWN = "unknown"


class EvidenceConfidence(str, Enum):
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass(frozen=True)
class EvidenceRecord:
    experiment_id: str
    observations: tuple[ProtocolObservation, ...]

    def __post_init__(self):
        normalized = tuple(self.observations)

        if not self.experiment_id:
            raise ValueError(
                "experiment_id is required"
            )

        if not all(
            isinstance(item, ProtocolObservation)
            for item in normalized
        ):
            raise TypeError(
                "observations must contain ProtocolObservation"
            )

        if any(
            item.experiment_id != self.experiment_id
            for item in normalized
        ):
            raise ValueError(
                "observation belongs to another experiment"
            )

        object.__setattr__(
            self,
            "observations",
            normalized,
        )

    @property
    def confirmed_count(self):
        return sum(
            item.outcome is ObservationOutcome.CONFIRMED
            for item in self.observations
        )

    @property
    def rejected_count(self):
        return sum(
            item.outcome is ObservationOutcome.REJECTED
            for item in self.observations
        )

    @property
    def repeat_count(self):
        return len(self.observations)

    @property
    def verdict(self):
        if not self.observations:
            return EvidenceVerdict.UNKNOWN

        if self.confirmed_count == len(self.observations):
            return EvidenceVerdict.SUPPORTED

        if self.rejected_count == len(self.observations):
            return EvidenceVerdict.REJECTED

        return EvidenceVerdict.UNKNOWN

    @property
    def confidence(self):
        if self.verdict is EvidenceVerdict.UNKNOWN:
            return EvidenceConfidence.NONE

        count = len(self.observations)

        if count >= 10:
            return EvidenceConfidence.HIGH

        if count >= 3:
            return EvidenceConfidence.MEDIUM

        return EvidenceConfidence.LOW

    def as_dict(self):
        return {
            "experiment_id": self.experiment_id,
            "repeat_count": self.repeat_count,
            "confirmed_count": self.confirmed_count,
            "rejected_count": self.rejected_count,
            "verdict": self.verdict.value,
            "confidence": self.confidence.value,
            "observations": [
                item.as_dict()
                for item in self.observations
            ],
        }
