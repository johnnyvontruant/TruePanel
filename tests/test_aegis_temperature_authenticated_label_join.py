from __future__ import annotations

import json
from pathlib import Path

from truepanel.aegis.reliability import AegisReliabilityEngine
from truepanel.aegis.temperature_authenticated_label_join import NAMESPACE
from truepanel.holodeck.aegis_temperature_authenticated_label_join import (
    run_temperature_authenticated_label_join_checkride,
)

ROOT = Path(__file__).resolve().parents[1]


def test_live_view_waits_for_complete_authenticated_labels():
    result = AegisReliabilityEngine().observe({"timestamp": 0.0})[
        "coverage_authenticated_label_join"
    ]
    assert result["status"] == "HOLD"
    assert result["blinded_manifest_ready"] is False
    assert result["labels_present"] is False
    assert result["label_signature_verified"] is False
    assert result["score_committed"] is False
    assert result["statistical_gates_passed"] is False
    assert result["field_validated"] is False
    assert result["deployment_authority"] is False
    assert result["hardware_authority"] is False


def test_authenticated_label_join_scores_once_and_seals_failures():
    report = run_temperature_authenticated_label_join_checkride()
    assert report["measurements"] == {
        "scenario_count": 13,
        "signing_ready_count": 2,
        "scored_count": 2,
        "hold_count": 9,
        "passing_score_count": 1,
        "failing_score_sealed_count": 1,
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
        "repeat_scores_accepted": 0,
        "case_exclusions": 0,
        "threshold_changes": 0,
        "field_validations": 0,
        "candidate_acceptances": 0,
        "candidate_installations": 0,
        "deployments": 0,
        "hardware_actions": 0,
        "production_writes": 0,
        "fixture_score_receipts_committed": 2,
        "private_key_inputs": 0,
        "signer_invocations_by_truepanel": 0,
        "fixture_private_keys_created": 1,
        "fixture_private_keys_retained": 0,
    }
    assert NAMESPACE == "truepanel-aegis-temperature-label-join-v1@truepanel"


def test_preserved_label_join_evidence_matches_checkride():
    report = run_temperature_authenticated_label_join_checkride()
    preserved = json.loads(
        (
            ROOT
            / "docs/evidence/aegis-temperature-authenticated-label-join-v1.json"
        ).read_text()
    )
    assert preserved == report


def test_mobile_view_exposes_one_shot_score_boundary():
    source = (ROOT / "truepanel/web/static/reliability-view.js").read_text()
    assert "Authenticated Label Join" in source
    assert "Every frozen case · one immutable score" in source
    assert "A failing authenticated score is sealed too" in source
    assert "@media(max-width:760px)" in source
