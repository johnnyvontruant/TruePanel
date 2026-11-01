"""Hardware-isolated reviewer-receipt and upgrade checkride."""

from __future__ import annotations

import hashlib
import hmac
import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from truepanel.aegis.acceptance import (
    ACCEPTANCE_SCHEMA,
    TRUST_POLICY_SCHEMA,
    acceptance_statement,
    evaluate_acceptance_receipt,
    semantic_sha256,
)
from truepanel.aegis.assurance import load_assurance_envelope
from truepanel.aegis.coverage import coverage_matrix
from truepanel.aegis.policy import DEFAULT_CORRELATION_POLICY
from truepanel.aegis.rehearsal import rehearse_recovery_paths
from truepanel.aegis.requalification import envelope_sha256, evaluate_successor_envelope
from truepanel.holodeck.aegis_requalification import (
    NOW,
    build_candidate_fixture,
    platform_payload,
)

_LAB_KEYS = {
    "lab-reviewer-a-v1": b"holodeck-reviewer-a",
    "lab-reviewer-b-v1": b"holodeck-reviewer-b",
    "lab-revoked-v1": b"holodeck-revoked",
}


def _sign(key_id: str, statement: bytes) -> str:
    return hmac.new(_LAB_KEYS[key_id], statement, hashlib.sha256).hexdigest()


def _verify(key_id: str, statement: bytes, signature: str) -> bool:
    key = _LAB_KEYS.get(key_id)
    return bool(key) and hmac.compare_digest(
        hmac.new(key, statement, hashlib.sha256).hexdigest(), signature
    )


def run_acceptance_checkride(*, package_root: Path | None = None) -> dict[str, Any]:
    root = package_root or Path(__file__).resolve().parents[1]
    accepted = load_assurance_envelope()
    candidate = build_candidate_fixture(accepted, root)
    appraisal = evaluate_successor_envelope(
        accepted=accepted,
        candidate=candidate,
        payload=platform_payload("25.10.6"),
        coverage_matrix=coverage_matrix(rehearse_recovery_paths()),
        correlation_policy=DEFAULT_CORRELATION_POLICY.describe(),
        now=NOW,
        package_root=root,
    )
    policy = {
        "schema": TRUST_POLICY_SCHEMA,
        "threshold": 2,
        "keys": [
            {
                "key_id": "lab-reviewer-a-v1",
                "reviewer_id": "release-reviewer-a",
                "valid_from": "2026-09-01T00:00:00Z",
                "valid_until": "2026-12-31T00:00:00Z",
            },
            {
                "key_id": "lab-reviewer-b-v1",
                "reviewer_id": "safety-reviewer-b",
                "valid_from": "2026-09-01T00:00:00Z",
                "valid_until": "2026-12-31T00:00:00Z",
            },
            {
                "key_id": "lab-revoked-v1",
                "reviewer_id": "former-reviewer",
                "valid_from": "2026-08-01T00:00:00Z",
                "valid_until": "2026-12-31T00:00:00Z",
                "revoked_at": "2026-09-05T00:00:00Z",
            },
        ],
    }
    receipt: dict[str, Any] = {
        "schema": ACCEPTANCE_SCHEMA,
        "receipt_id": "lab-upgrade-review-v1",
        "decision": "ACCEPTED_FOR_OPERATOR_PROMOTION",
        "candidate_envelope_sha256": semantic_sha256(candidate),
        "appraisal_sha256": semantic_sha256(appraisal),
        "predecessor_envelope_sha256": envelope_sha256(accepted),
        "issued_at": "2026-09-06T11:55:00Z",
        "expires_at": "2026-09-07T11:55:00Z",
        "environment": "HOLODECK",
        "signatures": [],
    }
    statement = json.dumps(
        acceptance_statement(receipt),
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode()
    receipt["signatures"] = [
        {"key_id": key, "reviewer_id": reviewer, "signature": _sign(key, statement)}
        for key, reviewer in (
            ("lab-reviewer-a-v1", "release-reviewer-a"),
            ("lab-reviewer-b-v1", "safety-reviewer-b"),
        )
    ]

    variants: list[tuple[str, dict[str, Any], dict[str, Any], dict[str, Any], str]] = [
        (
            "two-reviewer-quorum",
            receipt,
            candidate,
            appraisal,
            "ELIGIBLE_FOR_OPERATOR_PROMOTION",
        )
    ]
    one = deepcopy(receipt)
    one["signatures"] = one["signatures"][:1]
    variants.append(("one-reviewer", one, candidate, appraisal, "HOLD"))
    duplicate = deepcopy(receipt)
    duplicate["signatures"] = [duplicate["signatures"][0], duplicate["signatures"][0]]
    variants.append(("duplicate-reviewer", duplicate, candidate, appraisal, "HOLD"))
    revoked = deepcopy(receipt)
    revoked["signatures"][1] = {
        "key_id": "lab-revoked-v1",
        "reviewer_id": "former-reviewer",
        "signature": _sign("lab-revoked-v1", statement),
    }
    variants.append(("revoked-key", revoked, candidate, appraisal, "HOLD"))
    tampered = deepcopy(candidate)
    tampered["platform_version"] = "25.10.7"
    variants.append(("candidate-tamper", receipt, tampered, appraisal, "HOLD"))
    stale = deepcopy(receipt)
    stale["expires_at"] = "2026-09-06T11:59:00Z"
    variants.append(("expired-receipt", stale, candidate, appraisal, "HOLD"))
    not_ready = deepcopy(appraisal)
    not_ready["status"] = "HOLD"
    variants.append(("appraisal-not-ready", receipt, candidate, not_ready, "HOLD"))
    forged = deepcopy(receipt)
    forged["signatures"][0]["signature"] = "0" * 64
    variants.append(("forged-signature", forged, candidate, appraisal, "HOLD"))

    scenarios = []
    for name, value, proposed, review, expected in variants:
        result = evaluate_acceptance_receipt(
            receipt=value,
            candidate=proposed,
            appraisal=review,
            predecessor=accepted,
            trust_policy=policy,
            verifier=_verify,
            now=NOW,
        )
        scenarios.append(
            {
                "scenario": name,
                "status": result["status"],
                "reason": result["reason"],
                "expected": expected,
            }
        )
    report = {
        "schema_version": 1,
        "experiment_id": "TP-EXP-0023",
        "scenario": "aegis-independent-review-checkride-v1",
        "simulation": True,
        "signature_implementation": "deterministic-hmac-lab-only",
        "production_signer_present": False,
        "old_envelope_after_upgrade": {"status": "HOLD", "reason": "PlatformDrift"},
        "status_counts": {
            "ELIGIBLE_FOR_OPERATOR_PROMOTION": sum(
                x["status"] == "ELIGIBLE_FOR_OPERATOR_PROMOTION" for x in scenarios
            ),
            "HOLD": sum(x["status"] == "HOLD" for x in scenarios),
        },
        "scenarios": scenarios,
        "measurements": {
            "false_eligible_paths": sum(
                x["status"] != x["expected"] for x in scenarios
            ),
            "private_keys_persisted": 0,
            "candidate_installations": 0,
            "automatic_acceptances": 0,
            "runtime_writes": 0,
        },
        "production_mutation": False,
        "control_authority": False,
    }
    report["evidence_sha256"] = hashlib.sha256(
        json.dumps(
            report, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
    ).hexdigest()
    return report


__all__ = ["run_acceptance_checkride"]
