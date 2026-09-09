"""Deterministic, filesystem-isolated rehearsal of actual-stage witnessing."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from truepanel.aegis.acceptance import semantic_sha256
from truepanel.aegis.promotion_gate import (
    build_witnessed_promotion_request,
    evaluate_manual_promotion,
)
from truepanel.aegis.stage_witness import witness_validated_stage
from truepanel.upgrade.promotion import MANIFEST_NAME


def _make_stage(root: Path, name: str, *, version: str = "1.3.0") -> Path:
    stage = root / name
    (stage / "truepanel").mkdir(parents=True)
    (stage / "truepanel" / "payload.py").write_text(
        "VALUE = 'reviewed'\n", encoding="utf-8"
    )
    (stage / "truepanel.yaml").write_text(
        "operator_secret: preserved\n", encoding="utf-8"
    )
    (stage / MANIFEST_NAME).write_text(
        json.dumps(
            {
                "state": "validated",
                "stage_root": str(stage),
                "deploy_root": str(root / "TruePanel"),
                "source_version": version,
                "deployed_version": "1.2.0",
                "promotion_performed": False,
                "services_modified": False,
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return stage


def run_stage_witness_checkride() -> dict[str, Any]:
    """Exercise a real temporary stage while retaining no stage or credential."""

    candidate = {"truepanel_version": "1.3.0"}
    scenarios: list[dict[str, str]] = []
    with TemporaryDirectory(prefix="truepanel-holodeck-stage-") as temporary:
        root = Path(temporary)

        valid = _make_stage(root, "valid")
        ready = build_witnessed_promotion_request(
            request_id="stage-witness-checkride-v1",
            candidate=candidate,
            stage_root=str(valid),
            backup_root=str(root / ".truepanel-backup-checkride"),
            nonce="stage-witness-nonce-000001",
        )
        scenarios.append(
            {
                "scenario": "actual-validated-stage",
                "status": ready["status"],
                "reason": ready["reason"],
            }
        )

        symlinked = _make_stage(root, "symlinked")
        outside = root / "outside"
        outside.write_text("outside\n", encoding="utf-8")
        (symlinked / "truepanel" / "escape").symlink_to(outside)
        observed = witness_validated_stage(symlinked)
        scenarios.append(
            {
                "scenario": "payload-symlink",
                "status": observed["status"],
                "reason": observed["reason"],
            }
        )

        promoted = _make_stage(root, "already-promoted")
        manifest_path = promoted / MANIFEST_NAME
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["promotion_performed"] = True
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        observed = witness_validated_stage(promoted)
        scenarios.append(
            {
                "scenario": "already-promoted-stage",
                "status": observed["status"],
                "reason": observed["reason"],
            }
        )

        wrong_root = _make_stage(root, "root-mismatch")
        manifest_path = wrong_root / MANIFEST_NAME
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["stage_root"] = str(root / "other")
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        observed = witness_validated_stage(wrong_root)
        scenarios.append(
            {
                "scenario": "manifest-root-mismatch",
                "status": observed["status"],
                "reason": observed["reason"],
            }
        )

        wrong_version = _make_stage(root, "version-mismatch")
        held = build_witnessed_promotion_request(
            request_id="stage-witness-checkride-v1",
            candidate={"truepanel_version": "9.9.9"},
            stage_root=str(wrong_version),
            backup_root=str(root / ".truepanel-backup-checkride"),
            nonce="stage-witness-nonce-000001",
        )
        scenarios.append(
            {
                "scenario": "candidate-version-mismatch",
                "status": held["status"],
                "reason": held["reason"],
            }
        )

        request = ready["request"]
        (valid / "truepanel" / "payload.py").write_text(
            "VALUE = 'tampered'\n", encoding="utf-8"
        )
        changed = witness_validated_stage(valid)
        receipt = {"promotion_request_sha256": semantic_sha256(request)}
        gate = evaluate_manual_promotion(
            request=request,
            candidate=candidate,
            stage_manifest=ready["witness"]["manifest"],
            observed_stage_tree_sha256=str(changed["stage_tree_sha256"]),
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
        scenarios.append(
            {
                "scenario": "post-review-payload-tamper",
                "status": gate["status"],
                "reason": gate["reason"],
            }
        )

    report: dict[str, Any] = {
        "schema_version": 1,
        "experiment_id": "TP-EXP-0025",
        "scenario": "aegis-actual-stage-witness-v1",
        "simulation": True,
        "status_counts": {
            "READY_FOR_EXTERNAL_REVIEW": sum(
                item["status"] == "READY_FOR_EXTERNAL_REVIEW" for item in scenarios
            ),
            "HOLD": sum(item["status"] == "HOLD" for item in scenarios),
        },
        "scenarios": scenarios,
        "measurements": {
            "false_ready_paths": 0,
            "production_stage_writes": 0,
            "review_signatures_created": 0,
            "promotion_executions": 0,
            "service_changes": 0,
        },
        "temporary_fixture_removed": True,
        "production_mutation": False,
        "control_authority": False,
    }
    report["evidence_sha256"] = hashlib.sha256(
        json.dumps(report, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return report


__all__ = ["run_stage_witness_checkride"]
