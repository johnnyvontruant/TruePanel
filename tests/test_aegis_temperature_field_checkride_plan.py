from __future__ import annotations

import json
from pathlib import Path

from truepanel.aegis.reliability import AegisReliabilityEngine
from truepanel.aegis.temperature_field_checkride_plan import (
    expected_temperature_field_checkride_contract,
)
from truepanel.holodeck.aegis_temperature_field_checkride_plan import (
    run_temperature_field_checkride_plan_checkride,
)

ROOT = Path(__file__).resolve().parents[1]


def test_live_view_holds_before_content_bound_plan():
    result = AegisReliabilityEngine().observe({"timestamp": 0.0})[
        "coverage_field_checkride_plan"
    ]
    assert result["status"] == "HOLD"
    assert result["authenticated_appraisal_present"] is False
    assert result["plan_ready"] is False
    assert result["separate_confirmation_required"] is True
    assert result["confirmation_present"] is False
    assert result["recording_present"] is False
    assert result["battle_station_access"] is False
    assert result["capture_authority"] is False
    assert result["field_checkride_authority"] is False
    assert result["deployment_authority"] is False
    assert result["hardware_authority"] is False


def test_plan_contract_is_exact_passive_and_privacy_bounded():
    contract = expected_temperature_field_checkride_contract()
    assert contract["mode"] == "operator-supplied-recording-passive-replay-only"
    assert contract["source"]["live_host_path_allowed"] is False
    assert contract["source"]["truepanel_capture_allowed"] is False
    assert contract["privacy"]["classification"] == "sanitized"
    assert "serial-numbers" in contract["privacy"]["forbidden"]
    assert len(contract["passive_observations"]) == 7
    assert len(contract["abort_criteria"]) == 6
    assert len(contract["required_verification_evidence"]) == 7
    assert contract["separate_confirmation_required"] is True


def test_field_checkride_plan_is_ready_only_for_separate_confirmation():
    report = run_temperature_field_checkride_plan_checkride()
    assert report["measurements"] == {
        "scenario_count": 10,
        "plan_ready_count": 1,
        "hold_count": 9,
        "passive_observation_count": 7,
        "abort_criterion_count": 6,
        "required_evidence_count": 7,
        "coverage_total": 8,
        "coverage_trusted": 8,
        "coverage_gaps": 0,
        "shared_cooling_first_match_sample": 19,
        "isolated_threshold_first_match_sample": 46,
        "lead_samples": 27,
        "separate_confirmations": 0,
        "recordings_consumed": 0,
        "captures_started": 0,
        "battle_station_accesses": 0,
        "field_checkride_authorizations": 0,
        "field_validations": 0,
        "candidate_acceptances": 0,
        "candidate_installations": 0,
        "deployments": 0,
        "hardware_actions": 0,
        "runtime_writes": 0,
        "unsafe_ready_count": 0,
        "fixture_private_keys_created": 1,
        "fixture_private_keys_retained": 0,
    }


def test_preserved_field_checkride_plan_evidence_matches_rehearsal():
    preserved = json.loads(
        (
            ROOT
            / "docs/evidence/aegis-temperature-field-checkride-plan-v1.json"
        ).read_text()
    )
    assert preserved == run_temperature_field_checkride_plan_checkride()


def test_mobile_view_exposes_test_card_and_confirmation_boundary():
    source = (ROOT / "truepanel/web/static/reliability-view.js").read_text()
    assert "Field Checkride Test Card" in source
    assert "7 passive signals · 6 aborts · 7 evidence items" in source
    assert "Separate confirmation required" in source
    assert "No recording has been consumed" in source
    assert "BattleStation access: NO" in source
    assert "@media(max-width:760px)" in source
