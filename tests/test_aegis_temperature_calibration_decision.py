from __future__ import annotations

import json
from pathlib import Path

from truepanel.aegis.reliability import AegisReliabilityEngine
from truepanel.aegis.temperature_calibration_decision import NAMESPACE
from truepanel.holodeck.aegis_temperature_calibration_decision import (
    run_temperature_calibration_decision_checkride,
)

ROOT = Path(__file__).resolve().parents[1]


def test_live_view_requires_an_independent_review_before_decision():
    result = AegisReliabilityEngine().observe({"timestamp": 0.0})[
        "coverage_calibration_decision"
    ]
    assert result["status"] == "HOLD"
    assert result["independent_review_present"] is False
    assert result["operator_decision_present"] is False
    assert result["candidate_review_eligible"] is False
    assert result["candidate_accepted"] is False
    assert result["candidate_installed"] is False
    assert result["deployment_authority"] is False
    assert result["hardware_authority"] is False


def test_operator_decision_accepts_only_a_passing_independent_review():
    report = run_temperature_calibration_decision_checkride()
    assert report["measurements"] == {
        "scenario_count": 17,
        "signing_ready_count": 3,
        "accepted_count": 2,
        "operator_hold_count": 2,
        "hold_count": 10,
        "passing_accepts": 1,
        "passing_holds": 1,
        "failing_holds": 1,
        "failing_accepts": 0,
        "case_count": 440,
        "positive_cases": 40,
        "negative_cases": 400,
        "shared_cooling_index": 19,
        "isolated_threshold_index": 46,
        "lead_samples": 27,
        "decision_registry_writes": 4,
        "score_registry_writes": 0,
        "field_validations": 0,
        "candidate_acceptances": 0,
        "candidate_installations": 0,
        "deployments": 0,
        "hardware_actions": 0,
        "automatic_promotions": 0,
        "unsafe_ready_count": 0,
        "duplicate_replay_blocked": 1,
        "fixture_private_keys_created": 2,
        "fixture_private_keys_retained": 0,
    }
    assert NAMESPACE == "truepanel-aegis-temperature-calibration-decision-v1@truepanel"


def test_preserved_calibration_decision_evidence_matches_checkride():
    report = run_temperature_calibration_decision_checkride()
    preserved = json.loads(
        (ROOT / "docs/evidence/aegis-temperature-calibration-decision-v1.json").read_text()
    )
    assert preserved == report


def test_mobile_view_exposes_accept_or_hold_boundary():
    source = (ROOT / "truepanel/web/static/reliability-view.js").read_text()
    assert "Operator Calibration Decision" in source
    assert "Exact review · one signed ACCEPT or HOLD" in source
    assert "A failing review can only be held" in source
    assert "@media(max-width:760px)" in source
