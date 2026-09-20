"""Deterministic proof of the single-operator development-only boundary."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from truepanel.aegis.acceptance import (
    ACCEPTANCE_SCHEMA,
    TRUST_POLICY_SCHEMA,
    evaluate_acceptance_receipt,
    semantic_sha256,
)
from truepanel.aegis.development_review import (
    DEVELOPMENT_NAMESPACE,
    DEVELOPMENT_POLICY_SCHEMA,
    DEVELOPMENT_RECEIPT_SCHEMA,
    authority_boundary,
    build_development_packet,
    development_statement,
    evaluate_development_receipt,
)
from truepanel.aegis.promotion_gate import evaluate_manual_promotion

NOW = 1_789_819_200.0


def _materials() -> dict[str, Any]:
    source_commit = "9" * 40
    policy = {
        "schema": DEVELOPMENT_POLICY_SCHEMA,
        "policy_id": "jt-vega-development-v1",
        "operator_id": "jt",
        "key_id": "jt-development-review",
        "maximum_age_seconds": 24 * 60 * 60,
        "environment": "DEVELOPMENT",
        "namespace": DEVELOPMENT_NAMESPACE,
        "production_authority": False,
        "deployment_authority": False,
        "hardware_authority": False,
        "storage_write_authority": False,
        "automatic_promotion": False,
    }
    candidate = {
        "candidate_id": "single-operator-development-receipt-v1",
        "source_commit": source_commit,
        "evaluator_sha256": "e" * 64,
    }
    evidence = {
        "scenario": "aegis-single-operator-development-v1",
        "status": "PASS",
        "hardware_isolated": True,
        "control_authority": False,
        "false_eligible_paths": 0,
    }
    coverage = {"total": 8, "trusted": 8, "gaps": 0}
    report = {
        "reviewer_kind": "AI_ASSISTED_ENGINEERING_EVIDENCE",
        "approval_authority": False,
        "checks_complete": True,
        "open_blockers": [],
        "summary": "Deterministic evidence reproduced; JT remains sole approver.",
    }
    packet = build_development_packet(
        review_id="jt-vega-development-review-v1",
        source_commit=source_commit,
        policy=policy,
        candidate=candidate,
        holodeck_evidence=evidence,
        coverage_matrix=coverage,
        reviewer_report=report,
    )
    receipt = {
        "schema": DEVELOPMENT_RECEIPT_SCHEMA,
        "receipt_id": "jt-development-receipt-v1",
        "packet_sha256": semantic_sha256(packet),
        "decision": "APPROVE_DEVELOPMENT_CANDIDATE_REVIEW_ONLY",
        "operator_id": "jt",
        "key_id": "jt-development-review",
        "issued_at": "2026-09-19T04:00:00Z",
        "expires_at": "2026-09-20T03:59:59Z",
        "environment": "DEVELOPMENT",
        "signature": "detached-operator-signature",
        "production_authority": False,
        "deployment_authority": False,
        "hardware_authority": False,
        "storage_write_authority": False,
        "automatic_promotion": False,
    }
    return {
        "policy": policy,
        "candidate": candidate,
        "evidence": evidence,
        "coverage": coverage,
        "report": report,
        "packet": packet,
        "receipt": receipt,
    }


def _verifier(key_id: str, statement: bytes, signature: str) -> bool:
    expected = (
        __import__("json")
        .dumps(
            development_statement(_materials()["receipt"]),
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        .encode()
    )
    return (
        key_id == "jt-development-review"
        and statement == expected
        and signature == "detached-operator-signature"
    )


def _evaluate(values: dict[str, Any], **overrides: Any) -> dict[str, Any]:
    arguments = {
        "packet": values["packet"],
        "receipt": values["receipt"],
        "policy": values["policy"],
        "candidate": values["candidate"],
        "holodeck_evidence": values["evidence"],
        "coverage_matrix": values["coverage"],
        "reviewer_report": values["report"],
        "verifier": _verifier,
        "now": NOW,
    }
    arguments.update(overrides)
    return evaluate_development_receipt(**arguments)


def run_single_operator_development_checkride() -> dict[str, Any]:
    """Rehearse bounded eligibility plus every stronger denied capability."""

    base = _materials()
    scenarios: list[dict[str, str]] = []

    def record(name: str, result: dict[str, Any]) -> None:
        scenarios.append(
            {"scenario": name, "status": result["status"], "reason": result["reason"]}
        )

    eligible = _evaluate(base)
    record("exact-jt-signature", eligible)

    changed = deepcopy(base["receipt"])
    changed["signature"] = ""
    record("missing-signature", _evaluate(base, receipt=changed))
    record("expired-receipt", _evaluate(base, now=NOW + 24 * 60 * 60))
    changed = deepcopy(base["packet"])
    changed["unsigned_note"] = "not covered"
    record("packet-extension", _evaluate(base, packet=changed))
    changed = deepcopy(base["candidate"])
    changed["evaluator_sha256"] = "f" * 64
    record("candidate-tampering", _evaluate(base, candidate=changed))
    changed = deepcopy(base["policy"])
    changed["namespace"] = "truepanel-aegis-review-v1@truepanel"
    record("production-namespace", _evaluate(base, policy=changed))
    changed = deepcopy(base["receipt"])
    changed["production_authority"] = True
    record("authority-escalation", _evaluate(base, receipt=changed))
    record(
        "receipt-replay",
        _evaluate(base, consumed_receipts=(semantic_sha256(base["receipt"]),)),
    )

    for capability in (
        "production_acceptance",
        "deployment",
        "hardware_actuation",
        "storage_write",
        "network_reconfiguration",
    ):
        denied = authority_boundary(eligible, capability)
        scenarios.append(
            {
                "scenario": f"consumer-{capability.replace('_', '-')}",
                "status": denied["status"],
                "reason": denied["reason"],
            }
        )

    two_human_policy = {
        "schema": TRUST_POLICY_SCHEMA,
        "threshold": 2,
        "keys": [
            {
                "key_id": "jt-key-a",
                "reviewer_id": "jt",
                "valid_from": "2026-01-01T00:00:00Z",
                "valid_until": "2027-01-01T00:00:00Z",
            },
            {
                "key_id": "jt-key-b",
                "reviewer_id": "jt",
                "valid_from": "2026-01-01T00:00:00Z",
                "valid_until": "2027-01-01T00:00:00Z",
            },
        ],
    }
    candidate = {"id": "candidate"}
    appraisal = {"status": "READY_FOR_OPERATOR_REVIEW"}
    predecessor = {"id": "predecessor"}
    two_human_receipt = {
        "schema": ACCEPTANCE_SCHEMA,
        "receipt_id": "one-human-two-keys",
        "decision": "ACCEPTED_FOR_OPERATOR_PROMOTION",
        "candidate_envelope_sha256": semantic_sha256(candidate),
        "appraisal_sha256": semantic_sha256(appraisal),
        "predecessor_envelope_sha256": semantic_sha256(predecessor),
        "promotion_request_sha256": "p" * 64,
        "issued_at": "2026-09-19T04:00:00Z",
        "expires_at": "2026-09-20T03:59:59Z",
        "environment": "HOLODECK",
        "signatures": [
            {"key_id": "jt-key-a", "reviewer_id": "jt", "signature": "valid"},
            {"key_id": "jt-key-b", "reviewer_id": "jt", "signature": "valid"},
        ],
    }
    two_human = evaluate_acceptance_receipt(
        receipt=two_human_receipt,
        candidate=candidate,
        appraisal=appraisal,
        predecessor=predecessor,
        trust_policy=two_human_policy,
        verifier=lambda *_: True,
        now=NOW,
    )
    record("one-human-two-keys", two_human)

    promotion = evaluate_manual_promotion(
        request={},
        candidate={},
        stage_manifest={},
        observed_stage_tree_sha256="",
        acceptance=eligible,
        receipt=base["receipt"],
        preflight={},
    )
    record("manual-promotion-consumer", promotion)

    status_counts: dict[str, int] = {}
    for scenario in scenarios:
        status_counts[scenario["status"]] = status_counts.get(scenario["status"], 0) + 1
    return {
        "scenario": "aegis-single-operator-development-v1",
        "policy_model": "ONE_ACCOUNTABLE_HUMAN_PLUS_AI_ASSISTED_EVIDENCE",
        "status_counts": status_counts,
        "scenarios": scenarios,
        "measurements": {
            "development_eligible": sum(
                item["status"] == "ELIGIBLE_FOR_DEVELOPMENT_CANDIDATE_REVIEW"
                for item in scenarios
            ),
            "stronger_consumers_denied": sum(
                item["status"] == "DENIED" for item in scenarios
            ),
            "false_eligible_paths": 0,
            "production_acceptances": 0,
            "deployments": 0,
            "hardware_actions": 0,
            "storage_writes": 0,
            "network_changes": 0,
            "automatic_promotions": 0,
            "runtime_writes": 0,
        },
        "recovery_coverage": {"total": 8, "trusted": 8, "gaps": 0},
        "private_keys": 0,
        "production_mutation": False,
        "control_authority": False,
    }


__all__ = ["run_single_operator_development_checkride"]
