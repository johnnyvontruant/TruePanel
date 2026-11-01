"""
Recorded observations from protocol-discovery experiments.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum


class ObservationOutcome(str, Enum):
    CONFIRMED = "confirmed"
    REJECTED = "rejected"
    INCONCLUSIVE = "inconclusive"
    ERROR = "error"
    ABORTED = "aborted"


@dataclass(frozen=True)
class ProtocolObservation:
    experiment_id: str
    outcome: ObservationOutcome
    visible_effect: str = ""
    response_bytes: bytes = b""
    duration_ms: float = 0.0
    repeat_index: int = 1
    restored: bool = False
    notes: str = ""
    metadata: dict = field(default_factory=dict)
    timestamp: datetime = field(
        default_factory=lambda: datetime.now(UTC)
    )

    def __post_init__(self):
        if not self.experiment_id:
            raise ValueError(
                "experiment_id is required"
            )

        if not isinstance(
            self.outcome,
            ObservationOutcome,
        ):
            raise TypeError(
                "outcome must be an ObservationOutcome"
            )

        if isinstance(
            self.response_bytes,
            bytearray,
        ):
            object.__setattr__(
                self,
                "response_bytes",
                bytes(self.response_bytes),
            )

        if not isinstance(
            self.response_bytes,
            bytes,
        ):
            raise TypeError(
                "response_bytes must be bytes"
            )

        if self.duration_ms < 0:
            raise ValueError(
                "duration_ms cannot be negative"
            )

        if self.repeat_index < 1:
            raise ValueError(
                "repeat_index must be at least one"
            )

        object.__setattr__(
            self,
            "metadata",
            dict(self.metadata),
        )

    @property
    def response_hex(self):
        return self.response_bytes.hex(" ").upper()

    def as_dict(self):
        return {
            "experiment_id": self.experiment_id,
            "outcome": self.outcome.value,
            "visible_effect": self.visible_effect,
            "response_bytes": list(
                self.response_bytes
            ),
            "response_hex": self.response_hex,
            "duration_ms": self.duration_ms,
            "repeat_index": self.repeat_index,
            "restored": self.restored,
            "notes": self.notes,
            "metadata": dict(self.metadata),
            "timestamp": self.timestamp.isoformat(),
        }
