from __future__ import annotations

import json
from pathlib import Path

from truepanel.aegis.reliability import AegisReliabilityEngine
from truepanel.aegis.temperature_field_review_receipt import (
    NAMESPACE,
    pending_temperature_field_review_receipt,
)
from truepanel.holodeck.aegis_temperature_field_review_receipt import (
    run_temperature_field_review_receipt_checkride,
)

ROOT = Path(__file__).resolve().parents[1]


def test_live_field_review_waits_for_authenticated_recording():
    reliability = AegisReliabilityEngine().observe({"timestamp": 0.0})
    receipt = reliability["coverage_field_review_receipt"]
    assert receipt["status"] == "HOLD"
    assert receipt["development_signature_verified"] is False
    assert receipt["recording_present"] is False
    assert receipt["operator_review_signature_verified"] is False
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
        assert receipt[field] is False


def test_authenticated_projection_requires_a_separate_review_signature():
    receipt = pending_temperature_field_review_receipt(
        {"operator_signature_verified": True, "recording_present": True}
    )
    assert receipt["status"] == "ACTION_REQUIRED_FIELD_REVIEW_SIGNATURE"
    assert receipt["recording_present"] is True
    assert receipt["operator_opt_in"] is False
    assert receipt["eligible_for_calibration_review"] is False


def test_review_namespace_is_distinct_from_development_signature_namespace():
    assert NAMESPACE == "truepanel-aegis-temperature-field-review-v1@truepanel"


def test_holodeck_field_review_receipt_is_preserved_and_fails_closed():
    report = run_temperature_field_review_receipt_checkride()
    assert report["measurements"] == {
        "scenario_count": 12,
        "signing_ready_count": 1,
        "field_review_accepted_count": 2,
        "hold_count": 9,
        "unsafe_ready_count": 0,
        "source_paths_retained": 0,
        "private_key_inputs": 0,
        "signer_invocations_by_truepanel": 0,
        "fixture_private_keys_created": 2,
        "fixture_private_keys_retained": 0,
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
            / "docs/evidence/aegis-temperature-field-review-receipt-v1.json"
        ).read_text()
    )
    assert preserved == report


def test_mobile_view_exposes_field_review_and_authority_boundaries():
    source = (ROOT / "truepanel/web/static/reliability-view.js").read_text()
    assert "Content-Bound Field Review Receipt" in source
    assert "Opt-in bound:" in source
    assert "same protected public-key roster" in source
    assert "@media(max-width:760px)" in source
