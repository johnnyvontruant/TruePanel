from __future__ import annotations

import json
from pathlib import Path

from truepanel.aegis.reliability import AegisReliabilityEngine
from truepanel.aegis.temperature_field_checkride import (
    pending_temperature_field_checkride,
)
from truepanel.holodeck.aegis_temperature_field_checkride import (
    run_temperature_field_checkride,
)

ROOT = Path(__file__).resolve().parents[1]


def test_live_checkride_is_blocked_by_real_operator_signature():
    reliability = AegisReliabilityEngine().observe({"timestamp": 0.0})
    checkride = reliability["coverage_field_checkride"]
    assert checkride["status"] == "ACTION_REQUIRED_AUTHENTICATED_DEVELOPMENT_ACCEPTANCE"
    assert checkride["operator_signature_verified"] is False
    assert checkride["observation_present"] is False
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
        assert checkride[field] is False


def test_pending_projection_does_not_accept_status_without_verified_signature():
    result = pending_temperature_field_checkride(
        {
            "status": "AUTHENTICATED_DEVELOPMENT_ACCEPTED_FOR_REVIEW",
            "operator_signature_verified": False,
        }
    )
    assert result["status"] == "ACTION_REQUIRED_AUTHENTICATED_DEVELOPMENT_ACCEPTANCE"
    assert result["field_validated"] is False


def test_holodeck_checkride_is_preserved_and_never_claims_field_validation():
    report = run_temperature_field_checkride()
    assert report["measurements"] == {
        "scenario_count": 12,
        "simulation_rehearsal_passed_count": 1,
        "field_observation_review_ready_count": 1,
        "hold_count": 10,
        "false_field_validation_count": 0,
        "fixture_private_keys_created": 1,
        "fixture_private_keys_retained": 0,
        "production_keys": 0,
        "candidate_acceptances": 0,
        "candidate_installations": 0,
        "deployments": 0,
        "hardware_actions": 0,
        "runtime_writes": 0,
    }
    preserved = json.loads(
        (ROOT / "docs/evidence/aegis-temperature-field-checkride-v1.json").read_text()
    )
    assert preserved == report


def test_mobile_view_exposes_field_checkride_boundary():
    source = (ROOT / "truepanel/web/static/reliability-view.js").read_text()
    assert "Read-only Temperature Field Checkride" in source
    assert "Simulation success can prove the verification path" in source
    assert "Sanitized observation:" in source
    assert "@media(max-width:760px)" in source
