"""Deterministic HOLD presentation boundary for the isolated WINGMAN lab.

Only an upstream, trusted, typed policy decision may create a HoldEvidence.
Never infer authority from a model response, a natural-language source chunk,
a citation, or a client-controlled request. This module grants no release path.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from .service import WingmanServiceResult


class HoldKind(StrEnum):
    PHYSICAL_SERVICE = "PHYSICAL_SERVICE"
    AEGIS_AIRWORTHINESS = "AEGIS_AIRWORTHINESS"


_TRUSTED_SOURCE_IDS = {
    HoldKind.PHYSICAL_SERVICE: "status:operator_guidance",
    HoldKind.AEGIS_AIRWORTHINESS: "status:reliability",
}
_REASON_RE = re.compile(r"[A-Za-z][A-Za-z0-9_]{0,63}\Z")
_BAY_RE = re.compile(r"[1-9][0-9]{0,2}\Z")


@dataclass(frozen=True)
class HoldEvidence:
    """Trusted authoritative fact, independently provided by TruePanel policy.

    Caller must obtain values from trusted structured state, never parse
    model-visible prose or accept client-supplied trusted_holds.
    """

    kind: HoldKind
    reason_code: str
    source_id: str
    bay: int | None = None

    def __post_init__(self) -> None:
        if self.source_id != _TRUSTED_SOURCE_IDS[self.kind]:
            raise ValueError("HOLD source must match its trusted status section")
        if not _REASON_RE.fullmatch(self.reason_code):
            raise ValueError("HOLD reason must be a bounded machine code")
        if self.kind is HoldKind.PHYSICAL_SERVICE:
            if type(self.bay) is not int or not _BAY_RE.fullmatch(str(self.bay)):
                raise ValueError("Physical-service HOLD requires a verified bay")
        elif self.bay is not None:
            raise ValueError("Non-storage HOLD cannot assert a physical bay")


def render_hold(evidence: HoldEvidence) -> dict[str, Any]:
    """Generate operator text from templates, never from a model response."""

    if evidence.kind is HoldKind.PHYSICAL_SERVICE:
        assert evidence.bay is not None  # checked at construction
        headline = f"Bay {evidence.bay}: physical service HOLD"
        instructions = [
            f"Keep the drive in Bay {evidence.bay} installed.",
            "Backup verification is required before any operator-approved service.",
            "WINGMAN cannot authorize removal, replacement, or release this HOLD.",
        ]
    else:
        headline = f"AEGIS: HOLD ({evidence.reason_code})"
        instructions = [
            "AEGIS HOLD remains active; do not ignore or override it.",
            "WINGMAN cannot grant control authority or release this HOLD.",
        ]

    return {
        "kind": evidence.kind.value,
        "status": "HOLD",
        "reason_code": evidence.reason_code,
        "headline": headline,
        "instructions": instructions,
        "source_ids": [evidence.source_id],
        "control_authority": False,
        "production_mutation": False,
    }


def project_operator_view(
    result: WingmanServiceResult,
    *,
    trusted_holds: tuple[HoldEvidence, ...] = (),
) -> dict[str, Any]:
    """Safe presentation view, leaving the original model result untouched.

    Active HOLD always suppresses all generated text, not just obvious
    prohibited phrases: citations and pattern matching cannot prove semantic
    grounding. This is deliberately conservative until a separate evidence
    gate is designed and verified. Missing models do not erase trusted HOLD.
    """

    identities = [(item.kind, item.bay) for item in trusted_holds]
    if len(identities) != len(set(identities)):
        raise ValueError("Duplicate authoritative HOLD evidence")

    holds = [render_hold(item) for item in trusted_holds]
    model_available = result.status == "EXPLAINED" and result.advisory is not None
    if holds:
        status = "HOLD"
        summary = "Authoritative TruePanel HOLD. Generated explanation suppressed."
        explanation = None
        suppression_reason = "AUTHORITATIVE_HOLD"
    elif model_available:
        status = "EXPLAINED"
        summary = None
        # No trusted HOLD does not prove semantic safety for the model response.
        explanation = result.advisory
        suppression_reason = None
    else:
        status = "EXPLANATION_UNAVAILABLE"
        summary = "No validated generated explanation is available."
        explanation = None
        suppression_reason = "MODEL_RESULT_UNAVAILABLE"

    return {
        "schema_version": 1,
        "project": "WINGMAN",
        "status": status,
        "authoritative_holds": holds,
        "operator_notice": summary,
        "generated_explanation": explanation,
        "generated_explanation_suppressed": explanation is None,
        "suppression_reason": suppression_reason,
        "control_authority": False,
        "production_mutation": False,
        "hold_release_authorized": False,
        "evidence_origin": "TRUSTED_STRUCTURED_STATE",
        "advisory_only": True,
    }


__all__ = ["HoldEvidence", "HoldKind", "project_operator_view", "render_hold"]
