from __future__ import annotations

import json
from pathlib import Path

from truepanel.aegis.reliability import AegisReliabilityEngine
from truepanel.aegis.temperature_detector_result_binding import (
    pending_temperature_detector_result_binding,
)
from truepanel.holodeck.aegis_temperature_detector_result_binding import (
    run_temperature_detector_result_binding_checkride,
)

ROOT = Path(__file__).resolve().parents[1]


def test_live_result_binding_waits_for_authenticated_characterized_corpus():
    reliability = AegisReliabilityEngine().observe({"timestamp": 0.0})
    result = reliability["coverage_detector_result_binding"]
    assert result["status"] == "HOLD"
    assert result["label_blind_result_bound"] is False
    assert result["binding_signature_verified"] is False
    assert result["eligible_for_statistical_calibration_review"] is False
    assert result["corpus_write_performed"] is False
    assert result["field_validated"] is False
    assert result["candidate_installed"] is False
    assert result["deployment_authority"] is False
    assert result["hardware_authority"] is False


def test_characterized_corpus_still_requires_label_blind_results():
    result = pending_temperature_detector_result_binding(
        {"status": "CALIBRATION_CORPUS_CHARACTERIZED_FOR_INDEPENDENT_REVIEW"}
    )
    assert result["status"] == "ACTION_REQUIRED_LABEL_BLIND_DETECTOR_RESULT"
    assert result["eligible_for_statistical_calibration_review"] is False


def test_holodeck_result_binding_is_preserved_and_fails_closed():
    report = run_temperature_detector_result_binding_checkride()
    assert report["measurements"] == {
        "scenario_count": 10,
        "result_bound_count": 1,
        "hold_count": 9,
        "unsafe_ready_count": 0,
        "shared_cause_detection_sample": 19,
        "first_isolated_threshold_sample": 46,
        "detection_lead_samples": 27,
        "labels_accepted_by_detector": 0,
        "private_key_inputs": 0,
        "signer_invocations_by_truepanel": 0,
        "fixture_private_keys_created": 1,
        "fixture_private_keys_retained": 0,
        "corpus_writes": 0,
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
            / "docs/evidence/aegis-temperature-detector-result-binding-v1.json"
        ).read_text()
    )
    assert preserved == report


def test_mobile_view_exposes_label_blind_result_boundary():
    source = (ROOT / "truepanel/web/static/reliability-view.js").read_text()
    assert "Label-Blind Detector Evidence" in source
    assert "Prediction first · labels second · calibration only" in source
    assert "Predictions created after labels" in source
    assert "@media(max-width:760px)" in source
