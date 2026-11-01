"""
Protocol-discovery run models.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum

from .experiment import ProtocolExperiment
from .observation import ProtocolObservation


class RunState(str, Enum):
    CREATED = "created"
    RUNNING = "running"
    COMPLETED = "completed"
    ABORTED = "aborted"
    FAILED = "failed"


@dataclass(frozen=True)
class StepExecution:
    index: int
    total: int
    operation: str
    description: str
    payload: bytes = b""
    duration_ms: float = 0.0

    def __post_init__(self):
        if self.index < 1:
            raise ValueError(
                "step index must be at least one"
            )

        if self.total < 1:
            raise ValueError(
                "step total must be at least one"
            )

        if self.index > self.total:
            raise ValueError(
                "step index cannot exceed total"
            )

        if isinstance(self.payload, bytearray):
            object.__setattr__(
                self,
                "payload",
                bytes(self.payload),
            )

        if not isinstance(self.payload, bytes):
            raise TypeError(
                "payload must be bytes"
            )

        if self.duration_ms < 0:
            raise ValueError(
                "duration_ms cannot be negative"
            )

    @property
    def payload_hex(self):
        return self.payload.hex(" ").upper()

    def as_dict(self):
        return {
            "index": self.index,
            "total": self.total,
            "operation": self.operation,
            "description": self.description,
            "payload": list(self.payload),
            "payload_hex": self.payload_hex,
            "duration_ms": self.duration_ms,
        }


@dataclass(frozen=True)
class ProtocolRun:
    experiment: ProtocolExperiment
    state: RunState
    steps: tuple[StepExecution, ...]
    observations: tuple[ProtocolObservation, ...]
    started_at: datetime
    completed_at: datetime
    simulation: bool = True
    error: str = ""

    def __post_init__(self):
        if not isinstance(
            self.experiment,
            ProtocolExperiment,
        ):
            raise TypeError(
                "experiment must be a ProtocolExperiment"
            )

        if not isinstance(self.state, RunState):
            raise TypeError(
                "state must be a RunState"
            )

        object.__setattr__(
            self,
            "steps",
            tuple(self.steps),
        )
        object.__setattr__(
            self,
            "observations",
            tuple(self.observations),
        )

        if not isinstance(
            self.started_at,
            datetime,
        ):
            raise TypeError(
                "started_at must be datetime"
            )

        if not isinstance(
            self.completed_at,
            datetime,
        ):
            raise TypeError(
                "completed_at must be datetime"
            )

    @property
    def duration_ms(self):
        return max(
            0.0,
            (
                self.completed_at
                - self.started_at
            ).total_seconds()
            * 1000.0,
        )

    def as_dict(self):
        return {
            "experiment": self.experiment.as_dict(),
            "state": self.state.value,
            "simulation": self.simulation,
            "duration_ms": self.duration_ms,
            "started_at": self.started_at.astimezone(
                UTC
            ).isoformat(),
            "completed_at": self.completed_at.astimezone(
                UTC
            ).isoformat(),
            "error": self.error,
            "steps": [
                step.as_dict()
                for step in self.steps
            ],
            "observations": [
                observation.as_dict()
                for observation in self.observations
            ],
        }
