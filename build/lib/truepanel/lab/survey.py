"""
Opcode survey policy and report structures for Project Stargate.

This module defines which controller opcodes may be considered for surveys.
It performs no serial I/O and does not transmit commands.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable

from truepanel.diagnostics.protocol import A125Command
from truepanel.lab.classifier import ClassifiedResponse


class OpcodeRisk(str, Enum):
    SAFE_READ_ONLY = "SAFE_READ_ONLY"
    DOCUMENTED_WRITE = "DOCUMENTED_WRITE"
    EXPERIMENTAL_READ_ONLY = "EXPERIMENTAL_READ_ONLY"
    EXPERIMENTAL_STATEFUL = "EXPERIMENTAL_STATEFUL"
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

# Undocumented opcodes begin life as stateful unless research or vendor
# documentation provides evidence that they are read-only.
EXPERIMENTAL_READ_ONLY_OPCODES: frozenset[int] = frozenset()

EXPERIMENTAL_STATEFUL_OPCODES = frozenset(
    opcode
    for opcode in range(0x100)
    if opcode not in SAFE_READ_ONLY_OPCODES
    and opcode not in DOCUMENTED_WRITE_OPCODES
    and opcode not in BLOCKED_OPCODES
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

    @property
    def requires_explicit_authorization(self) -> bool:
        return self.risk in {
            OpcodeRisk.DOCUMENTED_WRITE,
            OpcodeRisk.EXPERIMENTAL_READ_ONLY,
            OpcodeRisk.EXPERIMENTAL_STATEFUL,
        }

    def as_dict(self) -> dict[str, object]:
        return {
            "opcode": self.opcode,
            "opcode_hex": self.opcode_hex,
            "risk": self.risk.value,
            "reason": self.reason,
            "permitted_by_default": self.permitted_by_default,
            "requires_explicit_authorization": (
                self.requires_explicit_authorization
            ),
        }


@dataclass(frozen=True)
class SurveyPlanEntry:
    opcode: int
    policy: OpcodePolicy

    @property
    def opcode_hex(self) -> str:
        return f"0x{self.opcode:02X}"

    def as_dict(self) -> dict[str, object]:
        return {
            "opcode": self.opcode,
            "opcode_hex": self.opcode_hex,
            "policy": self.policy.as_dict(),
        }


@dataclass(frozen=True)
class SurveyPlan:
    entries: tuple[SurveyPlanEntry, ...]
    allow_experimental_read_only: bool = False
    allow_experimental_stateful: bool = False
    allow_documented_writes: bool = False

    @property
    def opcodes(self) -> tuple[int, ...]:
        return tuple(entry.opcode for entry in self.entries)

    @property
    def count(self) -> int:
        return len(self.entries)

    def as_dict(self) -> dict[str, object]:
        return {
            "count": self.count,
            "opcodes": list(self.opcodes),
            "opcode_hex": [
                entry.opcode_hex
                for entry in self.entries
            ],
            "authorizations": {
                "experimental_read_only": (
                    self.allow_experimental_read_only
                ),
                "experimental_stateful": (
                    self.allow_experimental_stateful
                ),
                "documented_writes": (
                    self.allow_documented_writes
                ),
            },
            "entries": [
                entry.as_dict()
                for entry in self.entries
            ],
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


def normalize_opcode(opcode: int) -> int:
    opcode = int(opcode)

    if not 0 <= opcode <= 0xFF:
        raise ValueError("Opcode must fit in one byte")

    return opcode


def classify_opcode(opcode: int) -> OpcodePolicy:
    """Assign a safety policy to one opcode."""

    opcode = normalize_opcode(opcode)

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

    if opcode in EXPERIMENTAL_READ_ONLY_OPCODES:
        return OpcodePolicy(
            opcode=opcode,
            risk=OpcodeRisk.EXPERIMENTAL_READ_ONLY,
            reason=(
                "Undocumented opcode classified as read-only "
                "by prior research"
            ),
        )

    return OpcodePolicy(
        opcode=opcode,
        risk=OpcodeRisk.EXPERIMENTAL_STATEFUL,
        reason=(
            "Undocumented opcode with unknown state effects; "
            "treated as stateful by default"
        ),
    )


def validate_survey_opcodes(
    opcodes: Iterable[int],
    allow_experimental_read_only: bool = False,
    allow_experimental_stateful: bool = False,
    allow_documented_writes: bool = False,
) -> list[OpcodePolicy]:
    """
    Validate a proposed opcode survey.

    Blocked opcodes are always rejected. Every non-read-only category requires
    a separate explicit authorization.
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
            policy.risk == OpcodeRisk.EXPERIMENTAL_READ_ONLY
            and not allow_experimental_read_only
        ):
            raise PermissionError(
                f"{policy.opcode_hex} is experimental read-only; "
                "explicit authorization is required"
            )

        if (
            policy.risk == OpcodeRisk.EXPERIMENTAL_STATEFUL
            and not allow_experimental_stateful
        ):
            raise PermissionError(
                f"{policy.opcode_hex} is experimental stateful; "
                "stateful authorization is required"
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


def build_survey_plan(
    opcodes: Iterable[int],
    allow_experimental_read_only: bool = False,
    allow_experimental_stateful: bool = False,
    allow_documented_writes: bool = False,
) -> SurveyPlan:
    """Build a validated, immutable survey plan."""

    normalized = tuple(
        dict.fromkeys(
            normalize_opcode(opcode)
            for opcode in opcodes
        )
    )

    if not normalized:
        raise ValueError(
            "Survey plan must contain at least one opcode"
        )

    policies = validate_survey_opcodes(
        normalized,
        allow_experimental_read_only=(
            allow_experimental_read_only
        ),
        allow_experimental_stateful=(
            allow_experimental_stateful
        ),
        allow_documented_writes=allow_documented_writes,
    )

    entries = tuple(
        SurveyPlanEntry(
            opcode=opcode,
            policy=policy,
        )
        for opcode, policy in zip(normalized, policies)
    )

    return SurveyPlan(
        entries=entries,
        allow_experimental_read_only=(
            allow_experimental_read_only
        ),
        allow_experimental_stateful=(
            allow_experimental_stateful
        ),
        allow_documented_writes=allow_documented_writes,
    )
