from __future__ import annotations

import json
from pathlib import Path

from truepanel.aegis.reliability import AegisReliabilityEngine
from truepanel.aegis.temperature_intake_bound_detector_result import (
    pending_temperature_intake_bound_detector_result,
)
from truepanel.holodeck.aegis_temperature_intake_bound_detector_result import (
    run_temperature_intake_bound_detector_result_checkride,
)

ROOT = Path(__file__).resolve().parents[1]


def test_live_result_waits_without_claiming_authority():
    result = AegisReliabilityEngine().observe({"timestamp": 0.0})[
        "coverage_intake_bound_detector_result"
    ]
    assert result["status"] == "HOLD"
    assert result["receipt_bound"] is False
    assert result["eligible_for_calibration_binding"] is False
    assert result["deployment_authority"] is False
    assert result["hardware_authority"] is False


def test_accepted_intake_requests_separate_receipt_bound_replay():
    result = pending_temperature_intake_bound_detector_result(
        {"status": "LONG_WINDOW_RECORDING_ACCEPTED_FOR_LABEL_BLIND_REPLAY"}
    )
    assert result["status"] == "ACTION_REQUIRED_INTAKE_BOUND_DETECTOR_RESULT"
    assert result["receipt_bound"] is False


def test_holodeck_receipt_binding_is_preserved_and_fails_closed():
    report = run_temperature_intake_bound_detector_result_checkride()
    assert report["measurements"] == {
        "scenario_count": 10,
        "ready_count": 1,
        "hold_count": 9,
        "unsafe_ready_count": 0,
        "first_policy_match_index": 19,
        "first_isolated_threshold_index": 46,
        "correlation_lead_samples": 27,
        "intake_bypasses_accepted": 0,
        "labels_accepted": 0,
        "signer_invocations": 0,
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
            / "docs/evidence/aegis-temperature-intake-bound-detector-result-v1.json"
        ).read_text()
    )
    assert preserved == report


def test_mobile_view_exposes_receipt_binding_boundary():
    source = (ROOT / "truepanel/web/static/reliability-view.js").read_text()
    assert "Intake-Bound Detector Replay" in source
    assert "Receipt reconstructed · exact bytes replayed" in source
    assert (
        "Direct legacy replay, receipt substitution, and recording drift remain HOLD"
        in source
    )
    assert "@media(max-width:760px)" in source
