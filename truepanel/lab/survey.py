"""
Survey data structures for Project Stargate.

Survey plans are validated here before any future hardware runner is allowed
to transmit an opcode.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from truepanel.diagnostics.protocol import A125Command
from truepanel.lab.classifier import ClassifiedResponse


class OpcodeRisk(str, Enum):
    SAFE_READ_ONLY = "SAFE_READ_ONLY"
    DOCUMENTED_WRITE = "DOCUMENTED_WRITE"
    EXPERIMENTAL = "EXPERIMENTAL"
    BLOCKED = "BLOCKED"


SAFE_READ_ONLY_OPCODES = frozenset(
    {
        int(A125Command.GET_BOARD_ID),
        int(A125Command.GET_BUTTONS),
        int(A125Command.GET_PROTOCOL_VERSION),
    }
)

DOCUMENTED_WRITE_OPCODES = frozenset(
    {
        int(A125Command.DISPLAY_WRITE),
        int(A125Command.DISPLAY_CLEAR),
        int(A125Command.BACKLIGHT),
    }
)

BLOCKED_OPCODES = frozenset(
    {
        int(A125Command.RESET),
    }
)


@dataclass(frozen=True)
class OpcodePolicy:
    opcode: int
    risk: OpcodeRisk
    reason: str

    @property
    def opcode_hex(self) -> str:
        return f"0x{self.opcode:02X}"

    @property
    def permitted_by_default(self) -> bool:
        return self.risk == OpcodeRisk.SAFE_READ_ONLY

    def as_dict(self) -> dict[str, object]:
        return {
            "opcode": self.opcode,
            "opcode_hex": self.opcode_hex,
            "risk": self.risk.value,
            "reason": self.reason,
            "permitted_by_default": self.permitted_by_default,
        }


@dataclass(frozen=True)
class SurveyObservation:
    opcode: int
    response: ClassifiedResponse
    latency_ms: float | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            "opcode": self.opcode,
            "opcode_hex": f"0x{self.opcode:02X}",
            "latency_ms": self.latency_ms,
            "response": self.response.as_dict(),
        }


@dataclass
class SurveyReport:
    board_id: int | None = None
    protocol_version: int | None = None
    observations: list[SurveyObservation] = field(default_factory=list)

    def add(self, observation: SurveyObservation) -> None:
        self.observations.append(observation)

    def as_dict(self) -> dict[str, object]:
        return {
            "board_id": self.board_id,
            "board_id_hex": (
                f"0x{self.board_id:04X}"
                if self.board_id is not None
                else None
            ),
            "protocol_version": self.protocol_version,
            "protocol_version_hex": (
                f"0x{self.protocol_version:04X}"
                if self.protocol_version is not None
                else None
            ),
            "observation_count": len(self.observations),
            "observations": [
                observation.as_dict()
                for observation in self.observations
            ],
        }


def classify_opcode(opcode: int) -> OpcodePolicy:
    """Assign a safety policy to one opcode."""

    opcode = int(opcode)

    if not 0 <= opcode <= 0xFF:
        raise ValueError("Opcode must fit in one byte")

    if opcode in SAFE_READ_ONLY_OPCODES:
        return OpcodePolicy(
            opcode=opcode,
            risk=OpcodeRisk.SAFE_READ_ONLY,
            reason="Documented read-only query",
        )

    if opcode in DOCUMENTED_WRITE_OPCODES:
        return OpcodePolicy(
            opcode=opcode,
            risk=OpcodeRisk.DOCUMENTED_WRITE,
            reason="Documented command that changes display state",
        )

    if opcode in BLOCKED_OPCODES:
        return OpcodePolicy(
            opcode=opcode,
            risk=OpcodeRisk.BLOCKED,
            reason="Reset or potentially disruptive command",
        )

    return OpcodePolicy(
        opcode=opcode,
        risk=OpcodeRisk.EXPERIMENTAL,
        reason="Undocumented opcode; explicit authorization required",
    )


def validate_survey_opcodes(
    opcodes: list[int],
    allow_experimental: bool = False,
    allow_documented_writes: bool = False,
) -> list[OpcodePolicy]:
    """
    Validate a proposed opcode survey.

    Blocked opcodes are always rejected. Experimental and documented write
    commands require separate explicit authorization.
    """

    policies = [
        classify_opcode(opcode)
        for opcode in opcodes
    ]

    for policy in policies:
        if policy.risk == OpcodeRisk.BLOCKED:
            raise PermissionError(
                f"{policy.opcode_hex} is blocked: {policy.reason}"
            )

        if (
            policy.risk == OpcodeRisk.EXPERIMENTAL
            and not allow_experimental
        ):
            raise PermissionError(
                f"{policy.opcode_hex} is experimental; "
                "explicit authorization is required"
            )

        if (
            policy.risk == OpcodeRisk.DOCUMENTED_WRITE
            and not allow_documented_writes
        ):
            raise PermissionError(
                f"{policy.opcode_hex} changes display state; "
                "documented-write authorization is required"
            )

    return policies
