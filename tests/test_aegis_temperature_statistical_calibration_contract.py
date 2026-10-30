from __future__ import annotations

import json
from pathlib import Path

from truepanel.aegis.reliability import AegisReliabilityEngine
from truepanel.aegis.temperature_statistical_calibration_contract import (
    build_temperature_statistical_calibration_contract,
    validate_temperature_statistical_calibration_contract,
)
from truepanel.holodeck.aegis_temperature_statistical_calibration_contract import (
    run_temperature_statistical_calibration_contract_checkride,
)

ROOT = Path(__file__).resolve().parents[1]


def test_live_policy_is_locked_but_does_not_claim_scoring_or_authority():
    result = AegisReliabilityEngine().observe({"timestamp": 0.0})[
        "coverage_statistical_calibration_contract"
    ]
    assert result["status"] == "STATISTICAL_CALIBRATION_CONTRACT_PREDECLARED"
    assert result["locked_before_labels"] is True
    assert result["cohort_present"] is False
    assert result["scores_present"] is False
    assert result["eligible_for_independent_scoring"] is False
    assert result["field_validated"] is False
    assert result["deployment_authority"] is False
    assert result["hardware_authority"] is False


def test_policy_is_feasible_and_reconstructs_exactly():
    contract = build_temperature_statistical_calibration_contract(
        declared_at_utc="2026-10-22T04:30:00Z"
    )
    assert contract["feasibility"] == {
        "minimum_cohort_cases": 440,
        "perfect_sensitivity_wilson_lower": 0.912378,
        "zero_false_positive_rate_wilson_upper": 0.009512,
        "zero_abstention_rate_wilson_upper": 0.008655,
        "policy_mathematically_feasible": True,
    }
    result = validate_temperature_statistical_calibration_contract(contract)
    assert result["status"] == "STATISTICAL_CALIBRATION_CONTRACT_PREDECLARED"
    assert result["ready_for_blinded_cohort_collection"] is True
    assert result["eligible_for_independent_scoring"] is False


def test_holodeck_predeclaration_is_preserved_and_fails_closed():
    report = run_temperature_statistical_calibration_contract_checkride()
    assert report["measurements"] == {
        "scenario_count": 10,
        "predeclared_count": 1,
        "hold_count": 9,
        "unsafe_ready_count": 0,
        "minimum_positive_cases": 40,
        "minimum_negative_cases": 400,
        "minimum_cohort_cases": 440,
        "perfect_sensitivity_wilson_lower": 0.912378,
        "zero_false_positive_rate_wilson_upper": 0.009512,
        "zero_abstention_rate_wilson_upper": 0.008655,
        "labels_accepted": 0,
        "scores_accepted": 0,
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
            / "docs/evidence/aegis-temperature-statistical-calibration-contract-v1.json"
        ).read_text()
    )
    assert preserved == report


def test_mobile_view_exposes_policy_without_implying_validation():
    source = (ROOT / "truepanel/web/static/reliability-view.js").read_text()
    assert "Predeclared Statistical Contract" in source
    assert "Locked before labels · one independent score" in source
    assert "No threshold tuning, selective case exclusion" in source
    assert "@media(max-width:760px)" in source
