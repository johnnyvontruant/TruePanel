from __future__ import annotations

import json
from pathlib import Path

from truepanel.aegis.reliability import AegisReliabilityEngine
from truepanel.aegis.temperature_calibration_assessment import (
    pending_temperature_calibration_assessment,
)
from truepanel.holodeck.aegis_temperature_calibration_assessment import (
    run_temperature_calibration_assessment_checkride,
)

ROOT = Path(__file__).resolve().parents[1]


def test_live_assessment_waits_for_authenticated_corpus():
    reliability = AegisReliabilityEngine().observe({"timestamp": 0.0})
    result = reliability["coverage_calibration_assessment"]
    assert result["status"] == "HOLD"
    assert result["all_admission_signatures_reverified"] is False
    assert result["read_only_assessment"] is True
    assert result["field_validated"] is False
    assert result["candidate_accepted"] is False
    assert result["candidate_installed"] is False
    assert result["deployment_authority"] is False
    assert result["hardware_authority"] is False


def test_imported_case_still_requires_separate_assessment():
    result = pending_temperature_calibration_assessment(
        {"corpus_write_performed": True, "case_count": 1}
    )
    assert result["status"] == "ACTION_REQUIRED_CALIBRATION_ASSESSMENT"
    assert result["case_count"] == 1
    assert result["field_validated"] is False


def test_holodeck_assessment_is_preserved_and_fails_closed():
    report = run_temperature_calibration_assessment_checkride()
    assert report["measurements"] == {
        "scenario_count": 9,
        "review_ready_count": 1,
        "hold_count": 8,
        "authenticated_cases_in_ready_corpus": 4,
        "positive_cases": 2,
        "negative_cases": 2,
        "system_profiles": 2,
        "workload_classes": 2,
        "corpus_writes": 0,
        "field_validations": 0,
        "candidate_acceptances": 0,
        "candidate_installations": 0,
        "deployments": 0,
        "hardware_actions": 0,
        "runtime_writes": 0,
        "private_key_inputs": 0,
        "signer_invocations_by_truepanel": 0,
    }
    preserved = json.loads(
        (ROOT / "docs/evidence/aegis-temperature-calibration-assessment-v1.json")
        .read_text()
    )
    assert preserved == report


def test_mobile_view_exposes_read_only_assessment_boundary():
    source = (ROOT / "truepanel/web/static/reliability-view.js").read_text()
    assert "Calibration Evidence Assessment" in source
    assert "Read-only characterization · never validation" in source
    assert "Small, imbalanced, non-diverse, tampered, or unsigned corpora remain HOLD" in source
    assert "@media(max-width:760px)" in source
