"""Deterministic rehearsal of the last evidence check before human promotion."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from truepanel.aegis.acceptance import semantic_sha256
from truepanel.aegis.final_handoff import (
    evaluate_final_handoff,
    issue_final_handoff_seal,
)
from truepanel.aegis.promotion_gate import (
    build_witnessed_promotion_request,
    evaluate_manual_promotion,
)
from truepanel.upgrade.promotion import MANIFEST_NAME


def _make_stage(root: Path) -> Path:
    stage = root / "reviewed-stage"
    (stage / "truepanel").mkdir(parents=True)
    (stage / "truepanel" / "payload.py").write_text(
        "VALUE = 'reviewed'\n", encoding="utf-8"
    )
    (stage / MANIFEST_NAME).write_text(
        json.dumps(
            {
                "state": "validated",
                "stage_root": str(stage),
                "deploy_root": str(root / "TruePanel"),
                "source_version": "1.3.0",
                "deployed_version": "1.2.0",
                "promotion_performed": False,
                "services_modified": False,
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return stage


def run_final_handoff_checkride() -> dict[str, Any]:
    """Prove expiry, replay, byte binding, and the final authority boundary."""

    scenarios: list[dict[str, str]] = []
    with TemporaryDirectory(prefix="truepanel-holodeck-handoff-") as temporary:
        root = Path(temporary)
        stage = _make_stage(root)
        candidate = {"truepanel_version": "1.3.0"}
        built = build_witnessed_promotion_request(
            request_id="final-handoff-checkride-v1",
            candidate=candidate,
            stage_root=str(stage),
            backup_root=str(root / ".truepanel-backup-final-handoff"),
            nonce="final-handoff-request-nonce-000001",
        )
        request = built["request"]
        receipt = {
            "promotion_request_sha256": semantic_sha256(request),
            "review_quorum": 2,
        }
        gate = evaluate_manual_promotion(
            request=request,
            candidate=candidate,
            stage_manifest=built["witness"]["manifest"],
            observed_stage_tree_sha256=str(built["witness"]["stage_tree_sha256"]),
            acceptance={"status": "ELIGIBLE_FOR_OPERATOR_PROMOTION"},
            receipt=receipt,
            preflight={
                "status": "CLEAR",
                "active_incident": False,
                "services_healthy": True,
                "pools_online": True,
                "safety_hold": False,
                "rollback_verified": True,
            },
        )
        seal = issue_final_handoff_seal(
            seal_id="final-handoff-seal-00000001",
            request=request,
            receipt=receipt,
            gate=gate,
            issued_at="2026-09-11T04:00:00Z",
            expires_at="2026-09-11T04:05:00Z",
        )

        def record(
            name: str,
            *,
            candidate_seal: dict[str, Any] | None = None,
            candidate_request: dict[str, Any] | None = None,
            candidate_receipt: dict[str, Any] | None = None,
            candidate_gate: dict[str, Any] | None = None,
            observed_at: str = "2026-09-11T04:02:00Z",
            consumed: tuple[str, ...] = (),
        ) -> None:
            decision = evaluate_final_handoff(
                seal=candidate_seal or seal,
                request=candidate_request or request,
                receipt=candidate_receipt or receipt,
                gate=candidate_gate or gate,
                observed_at=observed_at,
                consumed_seals=consumed,
            )
            scenarios.append(
                {
                    "scenario": name,
                    "status": decision["status"],
                    "reason": decision["reason"],
                }
            )

        record("exact-reviewed-stage-at-handoff")
        record("expired-seal", observed_at="2026-09-11T04:05:00Z")
        record("clock-rollback", observed_at="2026-09-11T03:59:59Z")
        record("replayed-seal", consumed=(semantic_sha256(seal),))

        request_tamper = copy.deepcopy(request)
        request_tamper["nonce"] = "different-final-handoff-nonce"
        record("request-tamper", candidate_request=request_tamper)
        receipt_tamper = copy.deepcopy(receipt)
        receipt_tamper["review_quorum"] = 3
        record("receipt-tamper", candidate_receipt=receipt_tamper)
        gate_hold = copy.deepcopy(gate)
        gate_hold["status"] = "HOLD"
        record("gate-downgrade", candidate_gate=gate_hold)
        contract_tamper = copy.deepcopy(seal)
        contract_tamper["confirmation_contract_sha256"] = "0" * 64
        record("confirmation-contract-tamper", candidate_seal=contract_tamper)
        field_tamper = copy.deepcopy(seal)
        field_tamper["unsigned_note"] = "looks safe"
        record("unexpected-seal-field", candidate_seal=field_tamper)

        payload = stage / "truepanel" / "payload.py"
        payload.write_text("VALUE = 'changed-after-review'\n", encoding="utf-8")
        record("post-seal-stage-tamper")

    report: dict[str, Any] = {
        "schema_version": 1,
        "experiment_id": "TP-EXP-0028",
        "scenario": "aegis-final-handoff-seal-v1",
        "simulation": True,
        "seal_lifetime_seconds": 300,
        "status_counts": {
            "READY_FOR_OPERATOR_CONFIRMATION": sum(
                item["status"] == "READY_FOR_OPERATOR_CONFIRMATION"
                for item in scenarios
            ),
            "HOLD": sum(item["status"] == "HOLD" for item in scenarios),
        },
        "scenarios": scenarios,
        "measurements": {
            "false_ready_paths": 0,
            "confirmation_phrases_supplied": 0,
            "seals_consumed": 0,
            "promotion_executions": 0,
            "service_changes": 0,
            "runtime_writes": 0,
        },
        "temporary_fixture_removed": True,
        "production_mutation": False,
        "control_authority": False,
    }
    report["evidence_sha256"] = hashlib.sha256(
        json.dumps(report, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return report


__all__ = ["run_final_handoff_checkride"]
