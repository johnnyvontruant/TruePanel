import copy
import json
from pathlib import Path

import pytest

from truepanel.aegis.acceptance import semantic_sha256
from truepanel.aegis.final_handoff import (
    evaluate_final_handoff,
    issue_final_handoff_seal,
)
from truepanel.aegis.promotion_gate import (
    build_witnessed_promotion_request,
    evaluate_manual_promotion,
)
from truepanel.holodeck.aegis_final_handoff import run_final_handoff_checkride
from truepanel.upgrade.promotion import MANIFEST_NAME


def _chain(tmp_path: Path):
    stage = tmp_path / "stage"
    (stage / "truepanel").mkdir(parents=True)
    (stage / "truepanel" / "payload.py").write_text("VALUE = 1\n", encoding="utf-8")
    manifest = {
        "state": "validated",
        "stage_root": str(stage),
        "deploy_root": str(tmp_path / "TruePanel"),
        "source_version": "1.3.0",
        "deployed_version": "1.2.0",
        "promotion_performed": False,
        "services_modified": False,
    }
    (stage / MANIFEST_NAME).write_text(json.dumps(manifest), encoding="utf-8")
    candidate = {"truepanel_version": "1.3.0"}
    built = build_witnessed_promotion_request(
        request_id="handoff-unit-test",
        candidate=candidate,
        stage_root=str(stage),
        backup_root=str(tmp_path / ".truepanel-backup-unit"),
        nonce="handoff-unit-test-nonce-0001",
    )
    request = built["request"]
    receipt = {"promotion_request_sha256": semantic_sha256(request)}
    gate = evaluate_manual_promotion(
        request=request,
        candidate=candidate,
        stage_manifest=built["witness"]["manifest"],
        observed_stage_tree_sha256=built["witness"]["stage_tree_sha256"],
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
        seal_id="handoff-unit-seal-00000001",
        request=request,
        receipt=receipt,
        gate=gate,
        issued_at="2026-09-11T04:00:00Z",
        expires_at="2026-09-11T04:05:00Z",
    )
    return stage, request, receipt, gate, seal


def test_exact_handoff_is_ready_without_authority(tmp_path):
    _, request, receipt, gate, seal = _chain(tmp_path)
    decision = evaluate_final_handoff(
        seal=seal,
        request=request,
        receipt=receipt,
        gate=gate,
        observed_at="2026-09-11T04:04:59Z",
    )
    assert decision["status"] == "READY_FOR_OPERATOR_CONFIRMATION"
    assert decision["confirmation_supplied"] is False
    assert decision["seal_consumed"] is False
    assert decision["promotion_performed"] is False
    assert decision["control_authority"] is False


def test_issue_refuses_stale_or_unready_input(tmp_path):
    stage, request, receipt, gate, _ = _chain(tmp_path)
    stage.joinpath("truepanel/payload.py").write_text("changed\n", encoding="utf-8")
    with pytest.raises(ValueError, match="HandoffStageNotCurrent"):
        issue_final_handoff_seal(
            seal_id="handoff-unit-seal-00000002",
            request=request,
            receipt=receipt,
            gate=gate,
            issued_at="2026-09-11T04:00:00Z",
            expires_at="2026-09-11T04:05:00Z",
        )
    held_gate = copy.deepcopy(gate)
    held_gate["status"] = "HOLD"
    with pytest.raises(ValueError, match="HandoffSealPrerequisiteFailed"):
        issue_final_handoff_seal(
            seal_id="handoff-unit-seal-00000003",
            request=request,
            receipt=receipt,
            gate=held_gate,
            issued_at="2026-09-11T04:00:00Z",
            expires_at="2026-09-11T04:05:01Z",
        )


def test_unknown_seal_fields_and_replay_hold(tmp_path):
    _, request, receipt, gate, seal = _chain(tmp_path)
    altered = copy.deepcopy(seal)
    altered["comment"] = "unsigned"
    decision = evaluate_final_handoff(
        seal=altered,
        request=request,
        receipt=receipt,
        gate=gate,
        observed_at="2026-09-11T04:01:00Z",
    )
    assert decision["status"] == "HOLD"
    assert decision["reason"] == "SealFieldsUnexpected"

    decision = evaluate_final_handoff(
        seal=seal,
        request=request,
        receipt=receipt,
        gate=gate,
        observed_at="2026-09-11T04:01:00Z",
        consumed_seals=(semantic_sha256(seal),),
    )
    assert decision["status"] == "HOLD"
    assert decision["reason"] == "SealAlreadyConsumed"


def test_ready_label_cannot_hide_a_changed_gate(tmp_path):
    _, request, receipt, gate, seal = _chain(tmp_path)
    altered_gate = copy.deepcopy(gate)
    altered_gate["conditions"][0]["reason"] = "rewritten after sealing"
    decision = evaluate_final_handoff(
        seal=seal,
        request=request,
        receipt=receipt,
        gate=altered_gate,
        observed_at="2026-09-11T04:01:00Z",
    )
    assert decision["status"] == "HOLD"
    assert decision["reason"] == "ManualGateDigestMismatch"


def test_holodeck_checkride_is_deterministic():
    first = run_final_handoff_checkride()
    second = run_final_handoff_checkride()
    assert first == second
    assert first["status_counts"] == {"READY_FOR_OPERATOR_CONFIRMATION": 1, "HOLD": 9}
    assert all(value == 0 for value in first["measurements"].values())
