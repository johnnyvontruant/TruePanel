from __future__ import annotations

import json
from pathlib import Path

import pytest

from truepanel.aegis.field_workflow import (
    CONSENT_CONFIRMATION,
    FREEZE_CONFIRMATION,
    REVIEW_CONFIRMATION,
    assess_field_workflow,
    freeze_field_workflow,
    ingest_field_recording,
    initialize_field_workflow,
    review_field_case,
    run_field_workflow_smoke,
    workflow_status,
)
from truepanel.cli import build_parser
from truepanel.holodeck.aegis_corpus import builtin_corpus_path, load_corpus
from truepanel.holodeck.commands import handle_holodeck_command


def _source_case():
    manifest, _ = load_corpus()
    case = manifest["cases"][0]
    return case, builtin_corpus_path() / case["recording"]


def _initialize(path):
    return initialize_field_workflow(
        path,
        corpus_id="field-review-v1",
        retention_policy="delete on withdrawal; review annually",
        confirmation=CONSENT_CONFIRMATION,
    )


def _ingest(path, *, case_id="reviewed-cooling"):
    case, recording = _source_case()
    return ingest_field_recording(
        path,
        recording,
        case_id=case_id,
        challenge="reviewed-field-incident",
        system_profile="qnap-six-bay",
        workload_class="storage-workload",
        expected_shared_cooling=True,
        first_isolated_threshold_index=case["first_isolated_threshold_index"],
    )


def test_workflow_requires_exact_consent_and_empty_target(tmp_path):
    with pytest.raises(ValueError, match="consent"):
        initialize_field_workflow(
            tmp_path / "rejected",
            corpus_id="field-v1",
            retention_policy="delete on withdrawal",
            confirmation="yes",
        )

    root = tmp_path / "accepted"
    status = _initialize(root)
    assert status["state"] == "collecting"
    assert status["consent_recorded"] is True
    assert status["raw_identifiers_retained"] is False
    assert status["control_authority"] is False
    with pytest.raises(ValueError, match="non-empty"):
        _initialize(root)


def test_intake_rejects_data_that_only_becomes_safe_during_load(tmp_path):
    root = tmp_path / "workflow"
    _initialize(root)
    _, source = _source_case()
    records = [json.loads(line) for line in source.read_text().splitlines()]
    records[0]["telemetry"]["hostname"] = "private-nas"
    unsafe = tmp_path / "unsafe.jsonl"
    unsafe.write_text("\n".join(json.dumps(item) for item in records) + "\n")

    with pytest.raises(ValueError, match="not sanitized at rest"):
        ingest_field_recording(
            root,
            unsafe,
            case_id="unsafe",
            challenge="privacy-negative",
            system_profile="six-bay",
            workload_class="idle",
            expected_shared_cooling=False,
        )
    assert workflow_status(root)["case_count"] == 0


def test_review_freeze_and_assessment_are_immutable_and_fail_closed(tmp_path):
    root = tmp_path / "workflow"
    _initialize(root)
    _ingest(root)
    with pytest.raises(ValueError, match="unreviewed"):
        freeze_field_workflow(root, confirmation=FREEZE_CONFIRMATION)
    review_field_case(
        root, case_id="reviewed-cooling", confirmation=REVIEW_CONFIRMATION
    )
    frozen = freeze_field_workflow(root, confirmation=FREEZE_CONFIRMATION)
    assert frozen["state"] == "frozen"
    with pytest.raises(ValueError, match="expected 'collecting'"):
        _ingest(root, case_id="late-evidence")

    receipt = assess_field_workflow(root)
    assert receipt["stage"] == "lab_calibrated"
    assert receipt["eligible_for_field_validation"] is False
    assert receipt["production_validated"] is False
    assert receipt["release_review_required"] is True
    assert receipt["hardware_isolated"] is True
    assert workflow_status(root)["state"] == "assessed"
    assert assess_field_workflow(root) == receipt


def test_manifest_or_recording_tamper_breaks_assessment(tmp_path):
    root = tmp_path / "workflow"
    _initialize(root)
    _ingest(root)
    review_field_case(
        root, case_id="reviewed-cooling", confirmation=REVIEW_CONFIRMATION
    )
    freeze_field_workflow(root, confirmation=FREEZE_CONFIRMATION)
    recording = root / "recordings" / "reviewed-cooling.jsonl"
    recording.write_bytes(recording.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="digest mismatch"):
        assess_field_workflow(root)


def test_complete_smoke_replays_packaged_fixtures_without_claiming_field_trust(tmp_path):
    receipt = run_field_workflow_smoke(tmp_path / "smoke")
    assert receipt["stage"] == "lab_calibrated"
    assert receipt["measurements"]["true_positive_recordings"] == 1
    assert receipt["measurements"]["negative_frames"] == 141
    assert receipt["production_validated"] is False
    assert len(receipt["gaps"]) == 5

    preserved = (
        Path(__file__).resolve().parents[1]
        / "docs"
        / "evidence"
        / "aegis-field-workflow-smoke-v1.json"
    )
    assert json.loads(preserved.read_text(encoding="utf-8")) == receipt


def test_holodeck_field_smoke_cli_is_json_and_hardware_isolated(tmp_path, capsys):
    args = build_parser().parse_args(
        ["holodeck", "field-smoke", str(tmp_path / "cli-smoke")]
    )
    assert handle_holodeck_command(args) == 0
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["hardware_isolated"] is True
    assert receipt["control_authority"] is False


def test_mission_control_surfaces_mobile_field_workflow_contract():
    root = Path(__file__).resolve().parents[1]
    source = (root / "truepanel/web/static/reliability-view.js").read_text()
    assert "Field Evidence Workflow" in source
    assert "fieldWorkflowRows" in source
    assert 'grid-template-columns:1fr 1fr' in source
    assert 'field_workflow' in (
        root / "truepanel/aegis/policy.py"
    ).read_text()
