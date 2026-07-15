"""
Validated byte sequences for protocol-discovery experiments.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable


class StepOperation(str, Enum):
    TRANSMIT = "transmit"
    DELAY = "delay"
    DISPLAY_VERIFY = "display_verify"
    RESTORE = "restore"


def normalize_payload(payload) -> bytes:
    if isinstance(payload, bytearray):
        payload = bytes(payload)

    if not isinstance(payload, bytes):
        raise TypeError(
            "protocol payload must be bytes or bytearray"
        )

    if not payload:
        raise ValueError(
            "protocol payload cannot be empty"
        )

    return payload


@dataclass(frozen=True)
class ProtocolStep:
    """
    One step in a protocol experiment.

    TRANSMIT and RESTORE steps carry raw bytes. DELAY steps use delay_seconds.
    DISPLAY_VERIFY steps describe an operator-visible inspection checkpoint.
    """

    operation: StepOperation
    payload: bytes = b""
    delay_seconds: float = 0.0
    description: str = ""

    def __post_init__(self):
        if not isinstance(
            self.operation,
            StepOperation,
        ):
            raise TypeError(
                "operation must be a StepOperation"
            )

        if self.delay_seconds < 0:
            raise ValueError(
                "delay_seconds cannot be negative"
            )

        if self.operation in {
            StepOperation.TRANSMIT,
            StepOperation.RESTORE,
        }:
            object.__setattr__(
                self,
                "payload",
                normalize_payload(self.payload),
            )

        elif self.payload:
            raise ValueError(
                f"{self.operation.value} steps cannot carry payload"
            )

        if (
            self.operation is StepOperation.DELAY
            and self.delay_seconds <= 0
        ):
            raise ValueError(
                "delay steps require a positive delay"
            )

    @property
    def payload_hex(self):
        return self.payload.hex(" ").upper()

    def as_dict(self):
        return {
            "operation": self.operation.value,
            "payload": list(self.payload),
            "payload_hex": self.payload_hex,
            "delay_seconds": self.delay_seconds,
            "description": self.description,
        }


@dataclass(frozen=True)
class ProtocolSequence:
    """
    Ordered, immutable experiment steps.
    """

    steps: tuple[ProtocolStep, ...]

    def __post_init__(self):
        normalized = tuple(self.steps)

        if not normalized:
            raise ValueError(
                "protocol sequence requires at least one step"
            )

        if not all(
            isinstance(step, ProtocolStep)
            for step in normalized
        ):
            raise TypeError(
                "all sequence entries must be ProtocolStep"
            )

        object.__setattr__(
            self,
            "steps",
            normalized,
        )

    @classmethod
    def from_steps(
        cls,
        steps: Iterable[ProtocolStep],
    ):
        return cls(tuple(steps))

    @property
    def transmit_count(self):
        return sum(
            step.operation is StepOperation.TRANSMIT
            for step in self.steps
        )

    @property
    def has_restore(self):
        return any(
            step.operation is StepOperation.RESTORE
            for step in self.steps
        )

    def as_dict(self):
        return {
            "step_count": len(self.steps),
            "transmit_count": self.transmit_count,
            "has_restore": self.has_restore,
            "steps": [
                step.as_dict()
                for step in self.steps
            ],
        }

    def __len__(self):
        return len(self.steps)

    def __iter__(self):
        return iter(self.steps)
