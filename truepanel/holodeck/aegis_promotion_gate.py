"""Deterministic, non-executing manual-promotion checkride."""

from __future__ import annotations

import hashlib
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
from truepanel.aegis.promotion_gate import (
    build_promotion_request,
    evaluate_manual_promotion,
)
from truepanel.aegis.rehearsal import rehearse_recovery_paths
from truepanel.aegis.requalification import envelope_sha256, evaluate_successor_envelope
from truepanel.holodeck.aegis_acceptance import _sign, _verify
from truepanel.holodeck.aegis_requalification import (
    NOW,
    build_candidate_fixture,
    platform_payload,
)


def run_manual_promotion_checkride(
    *, package_root: Path | None = None
) -> dict[str, Any]:
    root = package_root or Path(__file__).resolve().parents[1]
    predecessor = load_assurance_envelope()
    candidate = build_candidate_fixture(predecessor, root)
    appraisal = evaluate_successor_envelope(
        accepted=predecessor,
        candidate=candidate,
        payload=platform_payload("25.10.6"),
        coverage_matrix=coverage_matrix(rehearse_recovery_paths()),
        correlation_policy=DEFAULT_CORRELATION_POLICY.describe(),
        now=NOW,
        package_root=root,
    )
    manifest = {
        "state": "validated",
        "source_root": "/lab/source",
        "stage_root": "/lab/.truepanel-stage-1.3.0",
        "deploy_root": "/lab/TruePanel",
        "source_version": candidate["truepanel_version"],
        "deployed_version": "1.2.0",
        "promotion_performed": False,
        "services_modified": False,
    }
    stage_digest = "a" * 64
    request = build_promotion_request(
        request_id="lab-promotion-v1",
        candidate=candidate,
        stage_manifest=manifest,
        stage_tree_sha256=stage_digest,
        backup_root="/lab/.truepanel-backup-before-1.3.0",
        nonce="checkride-nonce-0000000001",
    )
    receipt: dict[str, Any] = {
        "schema": ACCEPTANCE_SCHEMA,
        "receipt_id": "lab-promotion-review-v1",
        "decision": "ACCEPTED_FOR_OPERATOR_PROMOTION",
        "candidate_envelope_sha256": semantic_sha256(candidate),
        "appraisal_sha256": semantic_sha256(appraisal),
        "predecessor_envelope_sha256": envelope_sha256(predecessor),
        "promotion_request_sha256": semantic_sha256(request),
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
        ],
    }
    acceptance = evaluate_acceptance_receipt(
        receipt=receipt,
        candidate=candidate,
        appraisal=appraisal,
        predecessor=predecessor,
        trust_policy=policy,
        verifier=_verify,
        now=NOW,
    )
    preflight = {
        "status": "CLEAR",
        "active_incident": False,
        "services_healthy": True,
        "pools_online": True,
        "safety_hold": False,
        "rollback_verified": True,
    }
    scenarios = []

    def record(
        name,
        req=request,
        man=manifest,
        flight=preflight,
        digest=stage_digest,
        consumed=(),
        decision=acceptance,
    ):
        result = evaluate_manual_promotion(
            request=req,
            candidate=candidate,
            stage_manifest=man,
            observed_stage_tree_sha256=digest,
            acceptance=decision,
            receipt=receipt,
            preflight=flight,
            consumed_receipts=consumed,
        )
        scenarios.append(
            {
                "scenario": name,
                "status": result["status"],
                "reason": result["reason"],
                "promotion_performed": result["promotion_performed"],
                "services_modified": result["services_modified"],
            }
        )

    record("reviewed-pristine-stage")
    unsigned = deepcopy(acceptance)
    unsigned["status"] = "HOLD"
    record("independent-review-missing", decision=unsigned)
    record("receipt-replay", consumed=(semantic_sha256(receipt),))
    record("stage-tree-tamper", digest="b" * 64)
    dirty = deepcopy(manifest)
    dirty["services_modified"] = True
    record("stage-not-pristine", man=dirty)
    incident = deepcopy(preflight)
    incident.update({"active_incident": True, "status": "HOLD"})
    record("active-incident", flight=incident)
    no_rollback = deepcopy(preflight)
    no_rollback.update({"rollback_verified": False, "status": "HOLD"})
    record("rollback-unverified", flight=no_rollback)
    unsafe = deepcopy(request)
    unsafe["backup_root"] = "/tmp/backup"
    record("unsafe-backup-path", req=unsafe)
    wrong_version = deepcopy(manifest)
    wrong_version["source_version"] = "9.9.9"
    record("version-mismatch", man=wrong_version)

    report = {
        "schema_version": 1,
        "experiment_id": "TP-EXP-0024",
        "scenario": "aegis-manual-promotion-gate-v1",
        "simulation": True,
        "status_counts": {
            "READY_FOR_MANUAL_PROMOTION": sum(
                x["status"] == "READY_FOR_MANUAL_PROMOTION" for x in scenarios
            ),
            "HOLD": sum(x["status"] == "HOLD" for x in scenarios),
        },
        "scenarios": scenarios,
        "measurements": {
            "false_ready_paths": sum(
                (x["scenario"] == "reviewed-pristine-stage")
                != (x["status"] == "READY_FOR_MANUAL_PROMOTION")
                for x in scenarios
            ),
            "promotion_executions": 0,
            "receipt_consumptions": 0,
            "service_changes": 0,
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


__all__ = ["run_manual_promotion_checkride"]
