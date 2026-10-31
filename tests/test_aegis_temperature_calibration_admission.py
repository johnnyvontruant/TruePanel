from __future__ import annotations

import json
from pathlib import Path

from truepanel.aegis.reliability import AegisReliabilityEngine
from truepanel.aegis.temperature_calibration_admission import (
    NAMESPACE,
    pending_temperature_calibration_admission,
)
from truepanel.holodeck.aegis_temperature_calibration_admission import (
    run_temperature_calibration_admission_checkride,
)

ROOT = Path(__file__).resolve().parents[1]


def test_live_calibration_admission_waits_for_signed_field_review():
    reliability = AegisReliabilityEngine().observe({"timestamp": 0.0})
    admission = reliability["coverage_calibration_admission"]
    assert admission["status"] == "HOLD"
    assert admission["field_review_verified"] is False
    assert admission["labels_bound"] is False
    assert admission["admission_signature_verified"] is False
    assert admission["eligible_for_corpus_import"] is False
    assert admission["corpus_write_performed"] is False
    assert admission["field_validated"] is False
    assert admission["candidate_installed"] is False
    assert admission["deployment_authority"] is False
    assert admission["hardware_authority"] is False


def test_verified_field_review_still_requires_distinct_label_signature():
    admission = pending_temperature_calibration_admission(
        {"operator_review_signature_verified": True}
    )
    assert admission["status"] == "ACTION_REQUIRED_CALIBRATION_ADMISSION_SIGNATURE"
    assert admission["field_review_verified"] is True
    assert admission["eligible_for_corpus_import"] is False
    assert NAMESPACE == (
        "truepanel-aegis-temperature-calibration-admission-v1@truepanel"
    )


def test_holodeck_calibration_admission_is_preserved_and_fails_closed():
    report = run_temperature_calibration_admission_checkride()
    assert report["measurements"] == {
        "scenario_count": 12,
        "signing_ready_count": 1,
        "admitted_count": 2,
        "hold_count": 9,
        "unsafe_ready_count": 0,
        "source_paths_retained": 0,
        "private_key_inputs": 0,
        "signer_invocations_by_truepanel": 0,
        "fixture_private_keys_created": 2,
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
            / "docs/evidence/aegis-temperature-calibration-admission-v1.json"
        ).read_text()
    )
    assert preserved == report


def test_mobile_view_exposes_calibration_admission_boundary():
    source = (ROOT / "truepanel/web/static/reliability-view.js").read_text()
    assert "Calibration Corpus Admission" in source
    assert "Exact recording + exact labels" in source
    assert "Corpus write performed:" in source
    assert "A distinct namespace" in source
    assert "@media(max-width:760px)" in source
