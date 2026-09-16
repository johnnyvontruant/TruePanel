"""Deterministic adversarial checkride for identity-coverage appraisal."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from truepanel.aegis.coverage import coverage_matrix
from truepanel.aegis.coverage_appraisal import (
    appraise_identity_coverage_candidate,
    load_identity_appraisal_policy,
    semantic_sha256,
)
from truepanel.aegis.identity_coverage import (
    build_identity_coverage_candidate,
    rehearse_identity_coverage_contract,
)
from truepanel.aegis.rehearsal import rehearse_recovery_paths


def _redigest_evidence(evidence: dict[str, Any]) -> None:
    evidence.pop("evidence_sha256", None)
    evidence["evidence_sha256"] = semantic_sha256(evidence)


def _redigest_candidate(candidate: dict[str, Any]) -> None:
    candidate.pop("candidate_sha256", None)
    candidate["candidate_sha256"] = semantic_sha256(candidate)


def run_coverage_appraisal_rehearsal() -> dict[str, Any]:
    """Challenge every binding while remaining hardware isolated."""

    accepted = coverage_matrix(rehearse_recovery_paths())
    evidence = rehearse_identity_coverage_contract()
    candidate = build_identity_coverage_candidate(accepted, evidence)
    policy = load_identity_appraisal_policy()

    scenarios: list[dict[str, Any]] = []

    def evaluate(
        name: str,
        expected: str,
        *,
        accepted_value: dict[str, Any] | None = None,
        candidate_value: dict[str, Any] | None = None,
        policy_value: dict[str, Any] | None = None,
    ) -> None:
        result = appraise_identity_coverage_candidate(
            accepted_matrix=accepted_value or accepted,
            candidate=candidate_value or candidate,
            policy=policy_value or policy,
        )
        scenarios.append(
            {
                "name": name,
                "expected": expected,
                "actual": result["status"],
                "reason": result["reason"],
                "failed_conditions": [
                    item["condition"]
                    for item in result["conditions"]
                    if item["passed"] is not True
                ],
            }
        )

    evaluate("exact-candidate", "READY_FOR_INDEPENDENT_REVIEW")

    predecessor_drift = deepcopy(accepted)
    predecessor_drift["total"] = 9
    evaluate(
        "accepted-predecessor-drift",
        "HOLD",
        accepted_value=predecessor_drift,
    )

    unknown_field = deepcopy(candidate)
    unknown_field["unreviewed_extension"] = True
    _redigest_candidate(unknown_field)
    evaluate("unknown-candidate-field", "HOLD", candidate_value=unknown_field)

    evidence_drift = deepcopy(candidate)
    evidence_drift["identity_rehearsal"]["measurements"]["trusted"] = 99
    _redigest_evidence(evidence_drift["identity_rehearsal"])
    _redigest_candidate(evidence_drift)
    evaluate("identity-evidence-drift", "HOLD", candidate_value=evidence_drift)

    appraiser_drift = deepcopy(policy)
    appraiser_drift["appraiser_sha256"] = "0" * 64
    evaluate("appraiser-implementation-drift", "HOLD", policy_value=appraiser_drift)

    self_promoted = deepcopy(candidate)
    self_promoted["accepted"] = True
    _redigest_candidate(self_promoted)
    evaluate("candidate-self-promotion", "HOLD", candidate_value=self_promoted)

    false_outcomes = sum(
        item["actual"] != item["expected"] for item in scenarios
    )
    report = {
        "schema": "truepanel.holodeck-aegis-coverage-appraisal/v1",
        "experiment_id": "TP-EXP-0030",
        "simulation": True,
        "field_validated": False,
        "result": "PASS" if false_outcomes == 0 else "FAIL",
        "measurements": {
            "scenarios": len(scenarios),
            "ready": sum(
                item["expected"] == "READY_FOR_INDEPENDENT_REVIEW"
                for item in scenarios
            ),
            "holds": sum(item["expected"] == "HOLD" for item in scenarios),
            "false_outcomes": false_outcomes,
            "false_ready": sum(
                item["expected"] == "HOLD"
                and item["actual"] == "READY_FOR_INDEPENDENT_REVIEW"
                for item in scenarios
            ),
            "candidate_acceptances": 0,
            "runtime_writes": 0,
            "production_writes": 0,
        },
        "bindings": {
            "accepted_matrix_sha256": semantic_sha256(accepted),
            "candidate_sha256": candidate["candidate_sha256"],
            "identity_evidence_sha256": evidence["evidence_sha256"],
            "appraisal_policy_sha256": semantic_sha256(policy),
        },
        "scenarios": scenarios,
        "safety": {
            "live_provider_access": False,
            "hardware_actions": 0,
            "recovery_actions": 0,
            "automatic_acceptance": False,
            "control_authority": False,
        },
    }
    report["evidence_sha256"] = semantic_sha256(report)
    return report


__all__ = ["run_coverage_appraisal_rehearsal"]
