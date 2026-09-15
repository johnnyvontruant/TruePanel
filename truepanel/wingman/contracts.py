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

_REQUIRED_KEYS = frozenset(WINGMAN_RESPONSE_SCHEMA["required"])


def validate_grounded_answer(
    answer: dict[str, Any],
    *,
    allowed_source_ids: set[str],
) -> tuple[str, ...]:
    """Fail closed when generated advice is malformed or insufficiently grounded."""

    errors: list[str] = []

    keys = set(answer)
    if missing := _REQUIRED_KEYS - keys:
        errors.append("RequiredFieldsMissing:" + ",".join(sorted(missing)))
    if unexpected := keys - _REQUIRED_KEYS:
        errors.append("UnexpectedFields:" + ",".join(sorted(unexpected)))

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

    def validate_text(value: Any, label: str, max_length: int) -> None:
        if not isinstance(value, str):
            errors.append(f"{label}TextInvalid")
        elif len(value) > max_length:
            errors.append(f"{label}TextTooLong")

    def validate_ids(value: Any, label: str) -> None:
        if not isinstance(value, list) or not value:
            errors.append(f"{label}SourcesMissing")
            return
        if len(value) > 8:
            errors.append(f"{label}SourcesTooMany")
        if len(value) != len(set(item for item in value if isinstance(item, str))):
            errors.append(f"{label}SourcesDuplicate")
        for source_id in value:
            if not isinstance(source_id, str) or source_id not in allowed_source_ids:
                errors.append(f"{label}SourceUnknown")
                return

    validate_text(answer.get("summary"), "Summary", 1200)
    validate_ids(answer.get("summary_source_ids"), "Summary")

    observations = answer.get("observations")
    if not isinstance(observations, list):
        errors.append("ObservationsInvalid")
    else:
        if len(observations) > 8:
            errors.append("ObservationsTooMany")
        for index, item in enumerate(observations):
            if not isinstance(item, dict) or set(item) != {"text", "source_ids"}:
                errors.append(f"Observation{index}Malformed")
                continue
            validate_text(item.get("text"), f"Observation{index}", 800)
            validate_ids(item.get("source_ids"), f"Observation{index}")

    next_steps = answer.get("next_steps")
    required_step_keys = {"step", "why", "source_ids", "operator_action_required"}
    if not isinstance(next_steps, list):
        errors.append("NextStepsInvalid")
    else:
        if len(next_steps) > 8:
            errors.append("NextStepsTooMany")
        for index, item in enumerate(next_steps):
            if not isinstance(item, dict) or set(item) != required_step_keys:
                errors.append(f"NextStep{index}Malformed")
                continue
            validate_text(item.get("step"), f"NextStep{index}Step", 800)
            validate_text(item.get("why"), f"NextStep{index}Why", 800)
            validate_ids(item.get("source_ids"), f"NextStep{index}")
            if not isinstance(item.get("operator_action_required"), bool):
                errors.append(f"NextStep{index}OperatorActionInvalid")

    uncertainty = answer.get("uncertainty")
    if not isinstance(uncertainty, list):
        errors.append("UncertaintyInvalid")
    else:
        if len(uncertainty) > 8:
            errors.append("UncertaintyTooMany")
        for index, item in enumerate(uncertainty):
            validate_text(item, f"Uncertainty{index}", 500)

    return tuple(dict.fromkeys(errors))


__all__ = [
    "GroundingSource",
    "WINGMAN_RESPONSE_SCHEMA",
    "WingmanMode",
    "validate_grounded_answer",
]
