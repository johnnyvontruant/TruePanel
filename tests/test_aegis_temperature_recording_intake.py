from __future__ import annotations

import json
from pathlib import Path

from truepanel.aegis.reliability import AegisReliabilityEngine
from truepanel.aegis.temperature_recording_intake import (
    MAX_RECORDING_BYTES,
    pending_temperature_recording_intake,
)
from truepanel.history.black_box import MAX_BLACK_BOX_FRAME_BYTES
from truepanel.holodeck.aegis_temperature_recording_intake import (
    run_temperature_recording_intake_checkride,
)

ROOT = Path(__file__).resolve().parents[1]


def test_live_recording_intake_waits_for_signature_and_recording():
    reliability = AegisReliabilityEngine().observe({"timestamp": 0.0})
    intake = reliability["coverage_recording_intake"]
    assert intake["status"] == "ACTION_REQUIRED_AUTHENTICATED_DEVELOPMENT_ACCEPTANCE"
    assert intake["recording_present"] is False
    assert intake["capture_performed"] is False
    assert intake["private_key_accepted"] is False
    for field in (
        "field_validated",
        "production_validated",
        "candidate_accepted",
        "candidate_installed",
        "runtime_authority",
        "deployment_authority",
        "hardware_authority",
        "storage_write_authority",
        "network_authority",
        "automatic_promotion",
    ):
        assert intake[field] is False


def test_authenticated_pending_projection_still_requires_recording():
    result = pending_temperature_recording_intake(
        {"operator_signature_verified": True}
    )
    assert result["status"] == "HOLD"
    assert result["recording_present"] is False
    assert result["errors"] == []


def test_recording_limit_is_exactly_four_black_box_frames():
    assert MAX_RECORDING_BYTES == 4 * MAX_BLACK_BOX_FRAME_BYTES


def test_holodeck_recording_intake_is_preserved_and_fails_closed():
    report = run_temperature_recording_intake_checkride()
    assert report["measurements"] == {
        "scenario_count": 12,
        "simulation_rehearsal_passed_count": 1,
        "field_observation_review_ready_count": 1,
        "hold_count": 10,
        "unsafe_ready_count": 0,
        "source_paths_retained": 0,
        "capture_operations": 0,
        "private_key_inputs": 0,
        "fixture_private_keys_created": 1,
        "fixture_private_keys_retained": 0,
        "production_keys": 0,
        "field_validations": 0,
        "candidate_acceptances": 0,
        "candidate_installations": 0,
        "deployments": 0,
        "hardware_actions": 0,
        "runtime_writes": 0,
    }
    preserved = json.loads(
        (
            ROOT
            / "docs/evidence/aegis-temperature-recording-intake-v1.json"
        ).read_text()
    )
    assert preserved == report


def test_mobile_view_exposes_protected_recording_boundary():
    source = (ROOT / "truepanel/web/static/reliability-view.js").read_text()
    assert "Protected Black Box Recording Intake" in source
    assert "No capture, polling, or tailing" in source
    assert "Private key accepted:" in source
    assert "@media(max-width:760px)" in source
