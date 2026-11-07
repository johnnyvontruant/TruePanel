from __future__ import annotations

import json
from pathlib import Path

from truepanel.aegis.reliability import AegisReliabilityEngine
from truepanel.aegis.temperature_score_review import IMPLEMENTATION_ID
from truepanel.holodeck.aegis_temperature_score_review import (
    run_temperature_score_review_checkride,
)

ROOT = Path(__file__).resolve().parents[1]


def test_live_view_requires_an_immutable_score_before_review():
    result = AegisReliabilityEngine().observe({"timestamp": 0.0})[
        "coverage_score_review"
    ]
    assert result["status"] == "HOLD"
    assert result["score_receipt_present"] is False
    assert result["score_reconstructed"] is False
    assert result["review_receipt_created"] is False
    assert result["score_registry_read_only"] is True
    assert result["score_registry_writes"] == 0
    assert result["field_validated"] is False
    assert result["deployment_authority"] is False
    assert result["hardware_authority"] is False


def test_independent_review_reconstructs_passing_and_failing_scores():
    report = run_temperature_score_review_checkride()
    assert report["measurements"] == {
        "scenario_count": 12,
        "reviewed_count": 2,
        "hold_count": 10,
        "passing_scores_reconstructed": 1,
        "failing_scores_reconstructed": 1,
        "case_count": 440,
        "positive_cases": 40,
        "negative_cases": 400,
        "sensitivity_wilson_lower": 0.912378,
        "false_positive_rate_wilson_upper": 0.009512,
        "abstention_rate_wilson_upper": 0.008655,
        "median_lead_samples": 27.0,
        "p10_lead_samples": 27,
        "isolated_threshold_index": 46,
        "shared_cooling_index": 19,
        "lead_samples": 27,
        "score_registry_writes": 0,
        "score_registry_unchanged": True,
        "labels_changed": 0,
        "threshold_changes": 0,
        "score_re_evaluations": 0,
        "field_validations": 0,
        "candidate_acceptances": 0,
        "candidate_installations": 0,
        "deployments": 0,
        "hardware_actions": 0,
        "production_writes": 0,
        "unsafe_ready_count": 0,
        "fixture_private_keys_created": 1,
        "fixture_private_keys_retained": 0,
    }
    assert IMPLEMENTATION_ID == "truepanel-independent-score-review-python-v1"


def test_preserved_score_review_evidence_matches_checkride():
    report = run_temperature_score_review_checkride()
    preserved = json.loads(
        (
            ROOT
            / "docs/evidence/aegis-temperature-independent-score-review-v1.json"
        ).read_text()
    )
    assert preserved == report


def test_mobile_view_exposes_read_only_review_boundary():
    source = (ROOT / "truepanel/web/static/reliability-view.js").read_text()
    assert "Independent Score Review" in source
    assert "Reconstruct, compare, never rescore" in source
    assert "Passing and failing scores use the same review path" in source
    assert "@media(max-width:760px)" in source
