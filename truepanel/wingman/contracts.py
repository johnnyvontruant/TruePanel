"""Safety and grounding contracts for Project WINGMAN.

WINGMAN is an advisory translation layer. It may summarize or explain existing
TruePanel evidence, but it never becomes evidence itself and never gains
control authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class WingmanMode(StrEnum):
    """Operator-facing WINGMAN intents."""

    BRIEF = "brief"
    EXPLAIN = "explain"
    TROUBLESHOOT = "troubleshoot"


@dataclass(frozen=True)
class GroundingSource:
    """One bounded source that WINGMAN may cite.

    ``content`` must already be sanitized before it reaches this contract.
    WINGMAN never receives credentials, raw secrets, or unrestricted host data.
    """

    source_id: str
    kind: str
    title: str
    content: str

    def as_dict(self) -> dict[str, str]:
        return {
            "source_id": self.source_id,
            "kind": self.kind,
            "title": self.title,
            "content": self.content,
        }


WINGMAN_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "schema_version",
        "mode",
        "status",
        "summary",
        "summary_source_ids",
        "observations",
        "next_steps",
        "uncertainty",
        "control_authority",
        "production_mutation",
    ],
    "properties": {
        "schema_version": {"type": "integer", "const": 1},
        "mode": {
            "type": "string",
            "enum": [item.value for item in WingmanMode],
        },
        "status": {
            "type": "string",
            "enum": ["EXPLAINED", "INSUFFICIENT_EVIDENCE"],
        },
        "summary": {"type": "string", "maxLength": 1200},
        "summary_source_ids": {
            "type": "array",
            "minItems": 1,
            "maxItems": 8,
            "uniqueItems": True,
            "items": {"type": "string"},
        },
        "observations": {
            "type": "array",
            "maxItems": 8,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["text", "source_ids"],
                "properties": {
                    "text": {"type": "string", "maxLength": 800},
                    "source_ids": {
                        "type": "array",
                        "minItems": 1,
                        "maxItems": 8,
                        "uniqueItems": True,
                        "items": {"type": "string"},
                    },
                },
            },
        },
        "next_steps": {
            "type": "array",
            "maxItems": 8,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "step",
                    "why",
                    "source_ids",
                    "operator_action_required",
                ],
                "properties": {
                    "step": {"type": "string", "maxLength": 800},
                    "why": {"type": "string", "maxLength": 800},
                    "source_ids": {
                        "type": "array",
                        "minItems": 1,
                        "maxItems": 8,
                        "uniqueItems": True,
                        "items": {"type": "string"},
                    },
                    "operator_action_required": {"type": "boolean"},
                },
            },
        },
        "uncertainty": {
            "type": "array",
            "maxItems": 8,
            "items": {"type": "string", "maxLength": 500},
        },
        "control_authority": {"type": "boolean", "const": False},
        "production_mutation": {"type": "boolean", "const": False},
    },
}


def validate_grounded_answer(
    answer: dict[str, Any],
    *,
    allowed_source_ids: set[str],
) -> tuple[str, ...]:
    """Fail closed when generated advice is not grounded in supplied sources.

    This is intentionally small and dependency-free. Schema-constrained model
    output narrows the shape; this validator enforces the source and authority
    invariants that matter even when a provider returns malformed output.
    """

    errors: list[str] = []
    if answer.get("schema_version") != 1:
        errors.append("SchemaVersionMismatch")
    if answer.get("mode") not in {item.value for item in WingmanMode}:
        errors.append("ModeInvalid")
    if answer.get("status") not in {"EXPLAINED", "INSUFFICIENT_EVIDENCE"}:
        errors.append("StatusInvalid")
    if answer.get("control_authority") is not False:
        errors.append("ControlAuthorityMustRemainFalse")
    if answer.get("production_mutation") is not False:
        errors.append("ProductionMutationMustRemainFalse")

    def validate_ids(value: Any, label: str) -> None:
        if not isinstance(value, list) or not value:
            errors.append(f"{label}SourcesMissing")
            return
        for source_id in value:
            if not isinstance(source_id, str) or source_id not in allowed_source_ids:
                errors.append(f"{label}SourceUnknown")
                return

    validate_ids(answer.get("summary_source_ids"), "Summary")

    for index, item in enumerate(answer.get("observations") or []):
        if not isinstance(item, dict):
            errors.append(f"Observation{index}Malformed")
            continue
        validate_ids(item.get("source_ids"), f"Observation{index}")

    for index, item in enumerate(answer.get("next_steps") or []):
        if not isinstance(item, dict):
            errors.append(f"NextStep{index}Malformed")
            continue
        validate_ids(item.get("source_ids"), f"NextStep{index}")

    return tuple(dict.fromkeys(errors))


__all__ = [
    "GroundingSource",
    "WINGMAN_RESPONSE_SCHEMA",
    "WingmanMode",
    "validate_grounded_answer",
]
