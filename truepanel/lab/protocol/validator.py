"""
Validation for live protocol-discovery experiments.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .experiment import (
    ExperimentRisk,
    ProtocolExperiment,
)
from .policy import (
    A125_PREAMBLE,
    FORBIDDEN_OPCODES,
    ProtocolPolicy,
)
from .sequence import StepOperation


class ValidationReason(str, Enum):
    VALID = "valid"
    INVALID_EXPERIMENT = "invalid_experiment"
    CONTROLLER_MISMATCH = "controller_mismatch"
    FORBIDDEN_RISK = "forbidden_risk"
    TOO_MANY_STEPS = "too_many_steps"
    TOO_MANY_TRANSMITS = "too_many_transmits"
    TOO_MANY_REPEATS = "too_many_repeats"
    RESTORE_REQUIRED = "restore_required"
    RESTORE_NOT_FINAL = "restore_not_final"
    INVALID_PACKET = "invalid_packet"
    PACKET_TOO_LARGE = "packet_too_large"
    INVALID_PREAMBLE = "invalid_preamble"
    FORBIDDEN_OPCODE = "forbidden_opcode"
    OPCODE_NOT_APPROVED = "opcode_not_approved"
    DELAY_TOO_LONG = "delay_too_long"


@dataclass(frozen=True)
class ValidationResult:
    valid: bool
    reason: ValidationReason
    message: str
    step_index: int | None = None
    opcode: int | None = None

    @classmethod
    def allow(cls):
        return cls(
            valid=True,
            reason=ValidationReason.VALID,
            message="Protocol experiment is valid for live execution",
        )

    @classmethod
    def deny(
        cls,
        reason,
        message,
        *,
        step_index=None,
        opcode=None,
    ):
        return cls(
            valid=False,
            reason=reason,
            message=message,
            step_index=step_index,
            opcode=opcode,
        )

    def as_dict(self):
        return {
            "valid": self.valid,
            "reason": self.reason.value,
            "message": self.message,
            "step_index": self.step_index,
            "opcode": self.opcode,
            "opcode_hex": (
                ""
                if self.opcode is None
                else f"0x{self.opcode:02X}"
            ),
        }


class ProtocolExperimentValidator:
    def __init__(self, policy=None):
        self.policy = policy or ProtocolPolicy()

    def validate(
        self,
        experiment,
        *,
        controller_family="A125",
    ):
        if not isinstance(
            experiment,
            ProtocolExperiment,
        ):
            return ValidationResult.deny(
                ValidationReason.INVALID_EXPERIMENT,
                "Object is not a ProtocolExperiment",
            )

        if experiment.controller_family != controller_family:
            return ValidationResult.deny(
                ValidationReason.CONTROLLER_MISMATCH,
                (
                    "Experiment controller family does not match "
                    f"{controller_family}"
                ),
            )

        if experiment.risk is ExperimentRisk.FORBIDDEN:
            return ValidationResult.deny(
                ValidationReason.FORBIDDEN_RISK,
                "Forbidden experiments cannot execute",
            )

        if len(experiment.sequence) > self.policy.maximum_total_steps:
            return ValidationResult.deny(
                ValidationReason.TOO_MANY_STEPS,
                "Experiment exceeds the maximum number of steps",
            )

        if (
            experiment.sequence.transmit_count
            > self.policy.maximum_transmit_steps
        ):
            return ValidationResult.deny(
                ValidationReason.TOO_MANY_TRANSMITS,
                "Experiment exceeds the transmit-step limit",
            )

        if (
            experiment.repeat_count
            > self.policy.maximum_repeat_count
        ):
            return ValidationResult.deny(
                ValidationReason.TOO_MANY_REPEATS,
                "Experiment exceeds the repeat limit",
            )

        if (
            experiment.requires_restoration
            and not experiment.sequence.has_restore
        ):
            return ValidationResult.deny(
                ValidationReason.RESTORE_REQUIRED,
                "Live experiment requires a restore step",
            )

        if experiment.requires_restoration:
            final_step = experiment.sequence.steps[-1]

            if final_step.operation is not StepOperation.RESTORE:
                return ValidationResult.deny(
                    ValidationReason.RESTORE_NOT_FINAL,
                    "Restore must be the final sequence step",
                )

        for index, step in enumerate(
            experiment.sequence,
            start=1,
        ):
            if step.operation is StepOperation.DELAY:
                if (
                    step.delay_seconds
                    > self.policy.maximum_delay_seconds
                ):
                    return ValidationResult.deny(
                        ValidationReason.DELAY_TOO_LONG,
                        "Delay exceeds live policy limit",
                        step_index=index,
                    )

                continue

            if step.operation not in {
                StepOperation.TRANSMIT,
                StepOperation.RESTORE,
            }:
                continue

            payload = step.payload

            if len(payload) < 2:
                return ValidationResult.deny(
                    ValidationReason.INVALID_PACKET,
                    "A125 packet must contain preamble and opcode",
                    step_index=index,
                )

            if len(payload) > self.policy.maximum_packet_bytes:
                return ValidationResult.deny(
                    ValidationReason.PACKET_TOO_LARGE,
                    "Packet exceeds live policy byte limit",
                    step_index=index,
                )

            if payload[0] != A125_PREAMBLE:
                return ValidationResult.deny(
                    ValidationReason.INVALID_PREAMBLE,
                    "Packet does not use the A125 host preamble",
                    step_index=index,
                )

            opcode = payload[1]

            if opcode in FORBIDDEN_OPCODES:
                return ValidationResult.deny(
                    ValidationReason.FORBIDDEN_OPCODE,
                    f"Opcode 0x{opcode:02X} is forbidden",
                    step_index=index,
                    opcode=opcode,
                )

            if not self.policy.opcode_allowed(opcode):
                return ValidationResult.deny(
                    ValidationReason.OPCODE_NOT_APPROVED,
                    (
                        f"Opcode 0x{opcode:02X} is not approved "
                        "for this protocol session"
                    ),
                    step_index=index,
                    opcode=opcode,
                )

        return ValidationResult.allow()
