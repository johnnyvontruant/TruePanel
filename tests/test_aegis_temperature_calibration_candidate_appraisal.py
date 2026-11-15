from __future__ import annotations

import json
from pathlib import Path

from truepanel.aegis.reliability import AegisReliabilityEngine
from truepanel.aegis.temperature_calibration_candidate_appraisal import NAMESPACE
from truepanel.holodeck.aegis_temperature_calibration_candidate_appraisal import (
    run_temperature_calibration_candidate_appraisal_checkride,
)

ROOT = Path(__file__).resolve().parents[1]


def test_live_view_holds_before_authenticated_candidate_appraisal():
    result = AegisReliabilityEngine().observe({"timestamp": 0.0})[
        "coverage_calibration_candidate_appraisal"
    ]
    assert result["status"] == "HOLD"
    assert result["candidate_dossier_present"] is False
    assert result["operator_appraisal_present"] is False
    assert result["manual_field_checkride_planning_eligible"] is False
    assert result["field_checkride_authority"] is False
    assert result["candidate_accepted"] is False
    assert result["candidate_installed"] is False
    assert result["deployment_authority"] is False
    assert result["hardware_authority"] is False


def test_candidate_appraisal_approves_planning_only_and_fails_closed():
    report = run_temperature_calibration_candidate_appraisal_checkride()
    assert report["measurements"] == {
        "scenario_count": 12,
        "signing_ready_count": 2,
        "approved_for_manual_planning_count": 1,
        "operator_hold_count": 1,
        "hold_count": 8,
        "coverage_total": 8,
        "coverage_trusted": 8,
        "coverage_gaps": 0,
        "lead_samples": 27,
        "appraisal_registry_writes": 2,
        "field_checkride_authorizations": 0,
        "field_validations": 0,
        "candidate_acceptances": 0,
        "candidate_installations": 0,
        "deployments": 0,
        "hardware_actions": 0,
        "automatic_promotions": 0,
        "unsafe_ready_count": 0,
        "fixture_private_keys_created": 1,
        "fixture_private_keys_retained": 0,
    }
    assert NAMESPACE == (
        "truepanel-aegis-temperature-calibration-candidate-appraisal-v1@truepanel"
    )


def test_preserved_candidate_appraisal_evidence_matches_checkride():
    preserved = json.loads(
        (
            ROOT
            / "docs/evidence/aegis-temperature-calibration-candidate-appraisal-v1.json"
        ).read_text()
    )
    assert preserved == run_temperature_calibration_candidate_appraisal_checkride()


def test_mobile_view_exposes_planning_only_boundary():
    source = (ROOT / "truepanel/web/static/reliability-view.js").read_text()
    assert "Candidate Dossier Appraisal" in source
    assert "Exact dossier · one signed APPROVE or HOLD" in source
    assert "APPROVE permits planning only" in source
    assert "It does not authorize a field checkride" in source
    assert "@media(max-width:760px)" in source
