"""Draft a successor AIRWORTHINESS envelope from reviewed coverage evidence.

Drafting is intentionally distinct from appraisal, independent review,
acceptance, installation, and deployment.  Without an eligible review result
this module returns HOLD and does not construct an envelope.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from copy import deepcopy
from pathlib import Path
from typing import Any

from .assurance import coverage_contract_sha256
from .coverage_appraisal import APPRAISAL_SCHEMA, semantic_sha256
from .coverage_review import REVIEW_RECEIPT_SCHEMA, build_identity_review_packet
from .identity_coverage import validate_identity_coverage_candidate
from .requalification import envelope_sha256, renewal_contract_sha256

COVERAGE_ENVELOPE_DRAFT_SCHEMA = "truepanel.aegis-coverage-envelope-draft/v1"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _subject_digests(
    accepted_envelope: Mapping[str, Any], package_root: Path
) -> list[dict[str, str]]:
    names = {
        str(item.get("name") or "")
        for item in accepted_envelope.get("subjects", [])
        if isinstance(item, Mapping)
    }
    names.update(
        {
            "aegis/identity_coverage.py",
            "aegis/coverage_appraisal.py",
            "aegis/coverage_review.py",
            "aegis/coverage_envelope.py",
        }
    )
    subjects: list[dict[str, str]] = []
    for name in sorted(names):
        relative = Path(name)
        if not name or relative.is_absolute() or ".." in relative.parts:
            raise ValueError("EnvelopeSubjectPathInvalid")
        subjects.append({"name": name, "sha256": _sha256_file(package_root / relative)})
    return subjects


def prepare_coverage_successor_draft(
    *,
    accepted_envelope: Mapping[str, Any],
    accepted_matrix: Mapping[str, Any],
    candidate_matrix: Mapping[str, Any],
    appraisal: Mapping[str, Any],
    review_result: Mapping[str, Any],
    issued_at: str,
    expires_at: str,
    package_root: Path | None = None,
) -> dict[str, Any]:
    """Build an unaccepted draft only from the exact reviewed candidate."""

    root = package_root or Path(__file__).resolve().parents[1]
    conditions: list[dict[str, Any]] = []

    def add(name: str, passed: bool, reason: str) -> None:
        conditions.append({"condition": name, "passed": bool(passed), "reason": reason})

    predecessor_bound = (
        candidate_matrix.get("predecessor_sha256")
        == semantic_sha256(accepted_matrix)
        and not validate_identity_coverage_candidate(candidate_matrix)
    )
    add(
        "coverage_candidate",
        predecessor_bound,
        "CoverageCandidateBound" if predecessor_bound else "CoverageCandidateInvalid",
    )
    appraisal_bound = (
        appraisal.get("schema") == APPRAISAL_SCHEMA
        and appraisal.get("status") == "READY_FOR_INDEPENDENT_REVIEW"
        and appraisal.get("subject")
        == [
            {
                "name": "recovery-coverage-v2-candidate",
                "digest": {
                    "sha256": semantic_sha256(
                        {
                            key: value
                            for key, value in candidate_matrix.items()
                            if key != "candidate_sha256"
                        }
                    )
                },
            }
        ]
        and appraisal.get("candidate_accepted") is False
    )
    add(
        "coverage_appraisal",
        appraisal_bound,
        "CoverageAppraisalBound" if appraisal_bound else "CoverageAppraisalInvalid",
    )
    expected_packet_sha256 = semantic_sha256(
        build_identity_review_packet(
            accepted_matrix=accepted_matrix,
            candidate=candidate_matrix,
            appraisal=appraisal,
        )
    )
    review_eligible = (
        review_result.get("schema") == REVIEW_RECEIPT_SCHEMA
        and review_result.get("status") == "ELIGIBLE_FOR_SUCCESSOR_ENVELOPE_DRAFT"
        and review_result.get("reason") == "IndependentCoverageReviewVerified"
        and review_result.get("packet_sha256") == expected_packet_sha256
        and len(str(review_result.get("receipt_sha256") or "")) == 64
        and review_result.get("valid_reviewer_count") == 2
        and review_result.get("candidate_accepted") is False
        and review_result.get("successor_envelope_created") is False
        and review_result.get("automatic_acceptance") is False
        and review_result.get("control_authority") is False
    )
    add(
        "independent_review",
        review_eligible,
        "IndependentReviewEligible" if review_eligible else "IndependentReviewRequired",
    )

    failed = [item for item in conditions if item["passed"] is not True]
    if failed:
        return {
            "schema": COVERAGE_ENVELOPE_DRAFT_SCHEMA,
            "status": "HOLD",
            "reason": failed[0]["reason"],
            "conditions": conditions,
            "draft": None,
            "candidate_accepted": False,
            "successor_envelope_created": False,
            "candidate_installed": False,
            "runtime_writes": 0,
            "production_mutation": False,
            "control_authority": False,
        }

    accepted = deepcopy(dict(accepted_envelope))
    try:
        subjects = _subject_digests(accepted, root)
        renewal_digest = renewal_contract_sha256(root)
    except OSError:
        return {
            "schema": COVERAGE_ENVELOPE_DRAFT_SCHEMA,
            "status": "HOLD",
            "reason": "DraftSubjectUnavailable",
            "conditions": conditions,
            "draft": None,
            "candidate_accepted": False,
            "successor_envelope_created": False,
            "candidate_installed": False,
            "runtime_writes": 0,
            "production_mutation": False,
            "control_authority": False,
        }

    draft = deepcopy(accepted)
    draft.update(
        {
            "envelope_id": "aegis-airworthiness-identity-coverage-v2-draft",
            "predecessor_envelope_sha256": envelope_sha256(accepted),
            "issued_at": issued_at,
            "expires_at": expires_at,
            "coverage_sha256": coverage_contract_sha256(candidate_matrix),
            "subjects": subjects,
            "review_required": True,
            "automatic_acceptance": False,
            "renewal_contract_sha256": renewal_digest,
            "coverage_candidate_sha256": semantic_sha256(candidate_matrix),
            "coverage_appraisal_sha256": semantic_sha256(appraisal),
            "coverage_review_packet_sha256": review_result["packet_sha256"],
            "coverage_review_receipt_sha256": review_result["receipt_sha256"],
            "draft": True,
            "accepted": False,
            "installed": False,
        }
    )
    return {
        "schema": COVERAGE_ENVELOPE_DRAFT_SCHEMA,
        "status": "READY_FOR_INDEPENDENT_ENVELOPE_REVIEW",
        "reason": "ReviewedCoverageDrafted",
        "conditions": conditions,
        "draft": draft,
        "draft_sha256": envelope_sha256(draft),
        "candidate_accepted": False,
        "successor_envelope_created": True,
        "successor_envelope_accepted": False,
        "candidate_installed": False,
        "runtime_writes": 0,
        "production_mutation": False,
        "control_authority": False,
    }


__all__ = [
    "COVERAGE_ENVELOPE_DRAFT_SCHEMA",
    "prepare_coverage_successor_draft",
]
