from __future__ import annotations

import json
from pathlib import Path

from truepanel.aegis.reliability import AegisReliabilityEngine
from truepanel.aegis.temperature_calibration_candidate_appraisal import (
    NAMESPACE as APPRAISAL_NAMESPACE,
)
from truepanel.aegis.temperature_field_checkride_confirmation import NAMESPACE
from truepanel.holodeck.aegis_temperature_field_checkride_confirmation import (
    run_temperature_field_checkride_confirmation_checkride,
)

ROOT = Path(__file__).resolve().parents[1]


def test_live_view_holds_before_separate_confirmation():
    result = AegisReliabilityEngine().observe({"timestamp": 0.0})[
        "coverage_field_checkride_confirmation"
    ]
    assert result["status"] == "HOLD"
    assert result["plan_present"] is False
    assert result["confirmation_present"] is False
    assert result["operator_supplied_recording_review_eligible"] is False
    assert result["recording_present"] is False
    assert result["battle_station_access"] is False
    assert result["capture_authority"] is False
    assert result["field_checkride_authority"] is False
    assert result["deployment_authority"] is False
    assert result["hardware_authority"] is False


def test_confirmation_uses_a_distinct_signature_namespace():
    assert NAMESPACE != APPRAISAL_NAMESPACE
    assert (
        NAMESPACE
        == "truepanel-aegis-temperature-field-checkride-confirmation-v1@truepanel"
    )


def test_confirmation_rehearsal_is_fail_closed_and_non_operational():
    report = run_temperature_field_checkride_confirmation_checkride()
    assert report["measurements"] == {
        "scenario_count": 12,
        "signing_ready_count": 2,
        "recording_review_eligible_count": 1,
        "operator_hold_count": 1,
        "adversarial_hold_count": 8,
        "coverage_total": 8,
        "coverage_trusted": 8,
        "coverage_gaps": 0,
        "shared_cooling_first_match_sample": 19,
        "isolated_threshold_first_match_sample": 46,
        "lead_samples": 27,
        "confirmation_registry_writes": 3,
        "private_keys_accepted": 0,
        "truepanel_signer_invocations": 0,
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


def test_preserved_confirmation_evidence_matches_rehearsal():
    preserved = json.loads(
        (
            ROOT
            / "docs/evidence/aegis-temperature-field-checkride-confirmation-v1.json"
        ).read_text()
    )
    assert preserved == run_temperature_field_checkride_confirmation_checkride()


def test_mobile_view_exposes_confirmation_and_capture_boundary():
    source = (ROOT / "truepanel/web/static/reliability-view.js").read_text()
    assert "Offline Field Checkride Confirmation" in source
    assert "Exact plan · one signed CONFIRM or HOLD" in source
    assert "Operator-supplied recording review:" in source
    assert "Confirmation is a separate review act, not execution authority." in source
    assert "No recording is captured or consumed" in source
    assert "BattleStation access:" in source
    assert "@media(max-width:760px)" in source
