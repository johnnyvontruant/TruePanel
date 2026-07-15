"""
Project Stargate execution interlock.

This module makes policy decisions only. It does not write to serial ports,
invoke controller methods, or mutate hardware state.
"""

from dataclasses import dataclass, field
from enum import Enum
from uuid import uuid4


class DangerLevel(Enum):
    SAFE = "safe"
    EXPERIMENTAL = "experimental"
    DANGEROUS = "dangerous"
    FORBIDDEN = "forbidden"


class ExecutionMode(Enum):
    SIMULATION = "simulation"
    LIVE = "live"


class InterlockReason(Enum):
    ALLOWED = "allowed"
    SIMULATION_ALLOWED = "simulation_allowed"
    UNKNOWN_OPCODE = "unknown_opcode"
    FORBIDDEN_OPERATION = "forbidden_operation"
    LIVE_MODE_REQUIRED = "live_mode_required"
    SIMULATION_REQUIRED = "simulation_required"
    AUTHORIZATION_REQUIRED = "authorization_required"
    AUTHORIZATION_INVALID = "authorization_invalid"
    FINGERPRINT_REQUIRED = "fingerprint_required"
    FINGERPRINT_MISMATCH = "fingerprint_mismatch"
    COOLDOWN_ACTIVE = "cooldown_active"
    INVALID_REQUEST = "invalid_request"


@dataclass(frozen=True)
class ExecutionRequest:
    opcode: int
    name: str
    payload: bytes = b""
    danger_level: DangerLevel = DangerLevel.EXPERIMENTAL
    mode: ExecutionMode = ExecutionMode.SIMULATION
    request_id: str = field(
        default_factory=lambda: uuid4().hex
    )
    expected_controller_family: str = "A125"
    known_opcode: bool = False
    requires_live_hardware: bool = False

    def __post_init__(self):
        if not isinstance(self.opcode, int):
            raise TypeError("opcode must be an integer")

        if not 0 <= self.opcode <= 0xFF:
            raise ValueError(
                "opcode must be between 0x00 and 0xFF"
            )

        if not self.name or not self.name.strip():
            raise ValueError("name is required")

        if not isinstance(self.payload, bytes):
            raise TypeError("payload must be bytes")


@dataclass(frozen=True)
class InterlockDecision:
    allowed: bool
    reason: InterlockReason
    message: str
    simulation_only: bool = False
    cooldown_remaining: float = 0.0

    @classmethod
    def allow(
        cls,
        *,
        reason=InterlockReason.ALLOWED,
        message="Execution allowed",
        simulation_only=False,
    ):
        return cls(
            allowed=True,
            reason=reason,
            message=message,
            simulation_only=simulation_only,
        )

    @classmethod
    def deny(
        cls,
        reason,
        message,
        *,
        cooldown_remaining=0.0,
    ):
        return cls(
            allowed=False,
            reason=reason,
            message=message,
            cooldown_remaining=cooldown_remaining,
        )


class ExecutionInterlock:
    def __init__(
        self,
        *,
        cooldown=None,
        require_fingerprint=True,
    ):
        self.cooldown = cooldown
        self.require_fingerprint = require_fingerprint

    def evaluate(
        self,
        request,
        *,
        authorization=None,
        controller_family=None,
    ):
        if not isinstance(request, ExecutionRequest):
            return InterlockDecision.deny(
                InterlockReason.INVALID_REQUEST,
                "Request is not an ExecutionRequest",
            )

        if request.danger_level is DangerLevel.FORBIDDEN:
            return InterlockDecision.deny(
                InterlockReason.FORBIDDEN_OPERATION,
                "Forbidden operations cannot be executed",
            )

        if (
            request.requires_live_hardware
            and request.mode is not ExecutionMode.LIVE
        ):
            return InterlockDecision.deny(
                InterlockReason.LIVE_MODE_REQUIRED,
                "This operation requires live hardware mode",
            )

        if not request.known_opcode:
            if request.mode is ExecutionMode.LIVE:
                return InterlockDecision.deny(
                    InterlockReason.UNKNOWN_OPCODE,
                    "Unknown opcodes are denied in live mode",
                )

            return InterlockDecision.allow(
                reason=InterlockReason.SIMULATION_ALLOWED,
                message=(
                    "Unknown opcode permitted in simulation only"
                ),
                simulation_only=True,
            )

        if (
            request.danger_level
            is DangerLevel.EXPERIMENTAL
            and request.mode is ExecutionMode.LIVE
        ):
            return InterlockDecision.deny(
                InterlockReason.SIMULATION_REQUIRED,
                "Experimental operations are simulation-only",
            )

        if request.mode is ExecutionMode.SIMULATION:
            return InterlockDecision.allow(
                reason=InterlockReason.SIMULATION_ALLOWED,
                message="Simulation execution allowed",
                simulation_only=True,
            )

        fingerprint_decision = self._check_fingerprint(
            request,
            controller_family,
        )
        if fingerprint_decision is not None:
            return fingerprint_decision

        if request.danger_level is DangerLevel.DANGEROUS:
            authorization_decision = self._check_authorization(
                request,
                authorization,
            )
            if authorization_decision is not None:
                return authorization_decision

        cooldown_decision = self._check_cooldown(request)
        if cooldown_decision is not None:
            return cooldown_decision

        return InterlockDecision.allow(
            message="Live execution allowed",
        )

    def record_execution(self, request):
        if self.cooldown is not None:
            self.cooldown.record(self._cooldown_key(request))

    def _check_fingerprint(
        self,
        request,
        controller_family,
    ):
        if not self.require_fingerprint:
            return None

        if not controller_family:
            return InterlockDecision.deny(
                InterlockReason.FINGERPRINT_REQUIRED,
                "A live controller fingerprint is required",
            )

        if (
            controller_family
            != request.expected_controller_family
        ):
            return InterlockDecision.deny(
                InterlockReason.FINGERPRINT_MISMATCH,
                (
                    "Controller fingerprint does not match "
                    f"{request.expected_controller_family}"
                ),
            )

        return None

    @staticmethod
    def _check_authorization(
        request,
        authorization,
    ):
        if authorization is None:
            return InterlockDecision.deny(
                InterlockReason.AUTHORIZATION_REQUIRED,
                "Explicit authorization is required",
            )

        if not authorization.is_valid_for(
            request.request_id
        ):
            return InterlockDecision.deny(
                InterlockReason.AUTHORIZATION_INVALID,
                (
                    "Authorization is expired or belongs "
                    "to another request"
                ),
            )

        return None

    def _check_cooldown(self, request):
        if self.cooldown is None:
            return None

        key = self._cooldown_key(request)
        remaining = self.cooldown.remaining(key)

        if remaining > 0:
            return InterlockDecision.deny(
                InterlockReason.COOLDOWN_ACTIVE,
                (
                    "Execution cooldown active for "
                    f"{remaining:.3f} seconds"
                ),
                cooldown_remaining=remaining,
            )

        return None

    @staticmethod
    def _cooldown_key(request):
        return (
            request.expected_controller_family,
            request.opcode,
        )
