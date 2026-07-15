"""
Execution models for the Project Stargate laboratory.

These structures describe a survey execution without performing serial I/O.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from truepanel.lab.classifier import ClassifiedResponse
from truepanel.lab.survey import SurveyPlan


class ExecutionState(str, Enum):
    CREATED = "CREATED"
    VALIDATED = "VALIDATED"
    ARMED = "ARMED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    ABORTED = "ABORTED"
    FAILED = "FAILED"


@dataclass(frozen=True)
class ExecutionAuthorization:
    simulation: bool = True
    arming_phrase: str = ""

    @property
    def hardware_requested(self) -> bool:
        return not self.simulation

    def as_dict(self) -> dict[str, object]:
        return {
            "simulation": self.simulation,
            "hardware_requested": self.hardware_requested,
            "arming_phrase_supplied": bool(self.arming_phrase),
        }


@dataclass(frozen=True)
class ExecutionObservation:
    opcode: int
    success: bool
    simulated: bool
    latency_ms: float
    value: int | None = None
    response: ClassifiedResponse | None = None
    detail: str = ""

    @property
    def opcode_hex(self) -> str:
        return f"0x{self.opcode:02X}"

    @property
    def value_hex(self) -> str | None:
        if self.value is None:
            return None

        return f"0x{self.value:04X}"

    def as_dict(self) -> dict[str, object]:
        return {
            "opcode": self.opcode,
            "opcode_hex": self.opcode_hex,
            "success": self.success,
            "simulated": self.simulated,
            "latency_ms": self.latency_ms,
            "value": self.value,
            "value_hex": self.value_hex,
            "detail": self.detail,
            "response": (
                self.response.as_dict()
                if self.response is not None
                else None
            ),
        }


@dataclass
class ExecutionContext:
    plan: SurveyPlan
    authorization: ExecutionAuthorization
    cooldown_seconds: float = 0.10
    stop_on_failure: bool = True
    state: ExecutionState = ExecutionState.CREATED
    started_at: str = ""
    completed_at: str = ""
    abort_reason: str = ""
    observations: list[ExecutionObservation] = field(
        default_factory=list
    )

    @property
    def successes(self) -> int:
        return sum(
            1
            for observation in self.observations
            if observation.success
        )

    @property
    def failures(self) -> int:
        return sum(
            1
            for observation in self.observations
            if not observation.success
        )

    @property
    def healthy(self) -> bool:
        return (
            self.state == ExecutionState.COMPLETED
            and self.failures == 0
            and len(self.observations) == self.plan.count
        )

    def mark_started(self) -> None:
        self.started_at = datetime.now().isoformat(
            timespec="seconds"
        )
        self.state = ExecutionState.RUNNING

    def mark_completed(self) -> None:
        self.completed_at = datetime.now().isoformat(
            timespec="seconds"
        )
        self.state = ExecutionState.COMPLETED

    def abort(self, reason: str) -> None:
        self.abort_reason = str(reason)
        self.completed_at = datetime.now().isoformat(
            timespec="seconds"
        )
        self.state = ExecutionState.ABORTED

    def fail(self, reason: str) -> None:
        self.abort_reason = str(reason)
        self.completed_at = datetime.now().isoformat(
            timespec="seconds"
        )
        self.state = ExecutionState.FAILED

    def add(self, observation: ExecutionObservation) -> None:
        self.observations.append(observation)

    def as_dict(self) -> dict[str, object]:
        return {
            "state": self.state.value,
            "healthy": self.healthy,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "abort_reason": self.abort_reason,
            "cooldown_seconds": self.cooldown_seconds,
            "stop_on_failure": self.stop_on_failure,
            "successes": self.successes,
            "failures": self.failures,
            "plan": self.plan.as_dict(),
            "authorization": self.authorization.as_dict(),
            "observations": [
                observation.as_dict()
                for observation in self.observations
            ],
        }
