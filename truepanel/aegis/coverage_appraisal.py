"""Fail-closed appraisal of an unaccepted Recovery Coverage Matrix candidate.

The appraisal binds the accepted predecessor, candidate, deterministic identity
evidence, and the evaluator implementation.  Passing means only that the
candidate is ready for an independent reviewer; it never accepts or installs
the candidate.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .identity_coverage import build_identity_coverage_candidate

APPRAISAL_SCHEMA = "truepanel.aegis-coverage-appraisal/v1"
APPRAISAL_POLICY_SCHEMA = "truepanel.aegis-coverage-appraisal-policy/v1"
DEFAULT_POLICY_PATH = Path(__file__).with_name("identity_appraisal_policy.json")

_POLICY_FIELDS = {
    "schema",
    "policy_id",
    "accepted_matrix_sha256",
    "candidate_sha256",
    "identity_evidence_sha256",
    "appraiser_sha256",
    "expected_candidate_schema",
    "expected_candidate_status",
    "review_required",
    "automatic_acceptance",
}


def semantic_sha256(value: Any) -> str:
    """Return a stable digest for JSON-compatible semantic content."""

    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def appraiser_sha256(package_root: Path | None = None) -> str:
    root = package_root or Path(__file__).resolve().parents[1]
    return _sha256_file(root / "aegis/coverage_appraisal.py")


def load_identity_appraisal_policy(
    path: Path | None = None,
) -> dict[str, Any]:
    source = path or DEFAULT_POLICY_PATH
    try:
        policy = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("identity appraisal policy is unavailable") from error
    if not isinstance(policy, dict):
        raise ValueError("identity appraisal policy must be an object")
    return policy


def _without_digest(value: Mapping[str, Any], field: str) -> dict[str, Any]:
    result = dict(value)
    result.pop(field, None)
    return result


def appraise_identity_coverage_candidate(
    *,
    accepted_matrix: Mapping[str, Any],
    candidate: Mapping[str, Any],
    policy: Mapping[str, Any] | None = None,
    package_root: Path | None = None,
) -> dict[str, Any]:
    """Appraise exact, policy-bound content without granting acceptance."""

    try:
        governed_policy = dict(
            load_identity_appraisal_policy() if policy is None else policy
        )
    except (TypeError, ValueError):
        governed_policy = {}

    accepted = dict(accepted_matrix)
    proposed = dict(candidate)
    evidence_value = proposed.get("identity_rehearsal")
    evidence = dict(evidence_value) if isinstance(evidence_value, Mapping) else {}
    measurements_value = evidence.get("measurements")
    measurements = (
        dict(measurements_value)
        if isinstance(measurements_value, Mapping)
        else {}
    )
    false_outcomes = measurements.get("false_outcomes")
    conditions: list[dict[str, Any]] = []

    def add(name: str, passed: bool, reason: str) -> None:
        conditions.append(
            {"condition": name, "passed": bool(passed), "reason": reason}
        )

    policy_shape = (
        set(governed_policy) == _POLICY_FIELDS
        and governed_policy.get("schema") == APPRAISAL_POLICY_SCHEMA
        and governed_policy.get("review_required") is True
        and governed_policy.get("automatic_acceptance") is False
    )
    add(
        "appraisal_policy",
        policy_shape,
        "AppraisalPolicyMatched" if policy_shape else "AppraisalPolicyInvalid",
    )

    accepted_digest = semantic_sha256(accepted)
    predecessor_bound = (
        proposed.get("predecessor_sha256") == accepted_digest
        and governed_policy.get("accepted_matrix_sha256") == accepted_digest
    )
    add(
        "accepted_predecessor",
        predecessor_bound,
        "AcceptedPredecessorBound"
        if predecessor_bound
        else "AcceptedPredecessorMismatch",
    )

    candidate_digest = semantic_sha256(_without_digest(proposed, "candidate_sha256"))
    candidate_integrity = (
        proposed.get("candidate_sha256") == candidate_digest
        and governed_policy.get("candidate_sha256") == candidate_digest
    )
    add(
        "candidate_integrity",
        candidate_integrity,
        "CandidateDigestMatched"
        if candidate_integrity
        else "CandidateDigestMismatch",
    )

    evidence_digest = semantic_sha256(_without_digest(evidence, "evidence_sha256"))
    evidence_integrity = (
        evidence.get("evidence_sha256") == evidence_digest
        and governed_policy.get("identity_evidence_sha256") == evidence_digest
        and evidence.get("status") == "passed"
        and isinstance(false_outcomes, int)
        and not isinstance(false_outcomes, bool)
        and false_outcomes == 0
    )
    add(
        "identity_evidence",
        evidence_integrity,
        "IdentityEvidenceMatched"
        if evidence_integrity
        else "IdentityEvidenceMismatch",
    )

    try:
        expected_candidate = build_identity_coverage_candidate(accepted, evidence)
    except (TypeError, ValueError):
        expected_candidate = {}
    candidate_contract = (
        proposed == expected_candidate
        and proposed.get("schema")
        == governed_policy.get("expected_candidate_schema")
        and proposed.get("status")
        == governed_policy.get("expected_candidate_status")
        and proposed.get("accepted") is False
        and proposed.get("review_required") is True
        and proposed.get("automatic_acceptance") is False
    )
    add(
        "candidate_contract",
        candidate_contract,
        "CandidateContractMatched"
        if candidate_contract
        else "CandidateContractDrift",
    )

    try:
        observed_appraiser = appraiser_sha256(package_root)
    except OSError:
        observed_appraiser = ""
    appraiser_integrity = (
        len(str(governed_policy.get("appraiser_sha256") or "")) == 64
        and governed_policy.get("appraiser_sha256") == observed_appraiser
    )
    add(
        "appraiser_integrity",
        appraiser_integrity,
        "AppraiserDigestMatched"
        if appraiser_integrity
        else "AppraiserDigestMismatch",
    )

    failed = [item for item in conditions if item["passed"] is not True]
    status = "READY_FOR_INDEPENDENT_REVIEW" if not failed else "HOLD"
    reason = "CoverageCandidateAppraised" if not failed else failed[0]["reason"]
    return {
        "schema": APPRAISAL_SCHEMA,
        "status": status,
        "reason": reason,
        "subject": [
            {
                "name": "recovery-coverage-v2-candidate",
                "digest": {"sha256": candidate_digest},
            }
        ],
        "policy_id": governed_policy.get("policy_id"),
        "policy_sha256": semantic_sha256(governed_policy),
        "input_evidence": [
            {
                "name": "identity-continuity-rehearsal",
                "digest": {"sha256": evidence_digest},
            }
        ],
        "conditions": conditions,
        "review_required": True,
        "independent_review_complete": False,
        "candidate_accepted": False,
        "candidate_installed": False,
        "automatic_acceptance": False,
        "runtime_writes": 0,
        "production_mutation": False,
        "control_authority": False,
    }


__all__ = [
    "APPRAISAL_POLICY_SCHEMA",
    "APPRAISAL_SCHEMA",
    "appraise_identity_coverage_candidate",
    "appraiser_sha256",
    "load_identity_appraisal_policy",
    "semantic_sha256",
]
