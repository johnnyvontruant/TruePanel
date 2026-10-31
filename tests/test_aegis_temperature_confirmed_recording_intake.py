from __future__ import annotations

import json
from pathlib import Path

from truepanel.aegis.reliability import AegisReliabilityEngine
from truepanel.aegis.temperature_confirmed_recording_intake import (
    BASELINE_SAMPLE_COUNT,
    EXPECTED_SAMPLE_COUNT,
    RECORDING_SCHEMA,
)
from truepanel.holodeck.aegis_temperature_confirmed_recording_intake import (
    run_temperature_confirmed_recording_intake_checkride,
)

ROOT = Path(__file__).resolve().parents[1]


def test_live_view_holds_before_confirmation_and_recording():
    result = AegisReliabilityEngine().observe({"timestamp": 0.0})[
        "coverage_confirmed_recording_intake"
    ]
    assert result["status"] == "HOLD"
    assert result["confirmation_present"] is False
    assert result["recording_present"] is False
    assert result["recording_admitted"] is False
    assert result["capture_performed"] is False
    assert result["battle_station_access"] is False
    assert result["field_checkride_authority"] is False
    assert result["deployment_authority"] is False
    assert result["hardware_authority"] is False


def test_recording_contract_requires_baseline_and_complete_window():
    assert RECORDING_SCHEMA == "truepanel.black-box-temperature-field-recording/v1"
    assert BASELINE_SAMPLE_COUNT == 12
    assert EXPECTED_SAMPLE_COUNT == 48


def test_confirmed_recording_intake_is_fail_closed_and_non_operational():
    report = run_temperature_confirmed_recording_intake_checkride()
    assert report["measurements"] == {
        "scenario_count": 13,
        "ready_count": 1,
        "hold_count": 12,
        "sample_count": 48,
        "baseline_sample_count": 12,
        "signal_count": 7,
        "coverage_total": 8,
        "coverage_trusted": 8,
        "coverage_gaps": 0,
        "shared_cooling_first_match_sample": 19,
        "isolated_threshold_first_match_sample": 46,
        "lead_samples": 27,
        "intake_receipt_writes": 2,
        "source_paths_retained": 0,
        "recordings_captured": 0,
        "recordings_replayed": 0,
        "battle_station_accesses": 0,
        "field_checkride_authorizations": 0,
        "field_validations": 0,
        "candidate_acceptances": 0,
        "candidate_installations": 0,
        "deployments": 0,
        "hardware_actions": 0,
        "runtime_writes": 0,
        "unsafe_ready_count": 0,
        "fixture_private_keys_created": 1,
        "fixture_private_keys_retained": 0,
    }


def test_preserved_confirmed_recording_evidence_matches_rehearsal():
    preserved = json.loads(
        (
            ROOT / "docs/evidence/aegis-temperature-confirmed-recording-intake-v1.json"
        ).read_text()
    )
    assert preserved == run_temperature_confirmed_recording_intake_checkride()


def test_mobile_view_exposes_intake_and_capture_boundary():
    source = (ROOT / "truepanel/web/static/reliability-view.js").read_text()
    assert "Confirmed Recording Intake" in source
    assert "Operator supplied · canonical · sanitized · digest bound" in source
    assert "Privacy:" in source
    assert "Stable baseline:" in source
    assert "Capture performed:" in source
    assert "It does not replay, label, validate, promote, deploy" in source
    assert "@media(max-width:760px)" in source
