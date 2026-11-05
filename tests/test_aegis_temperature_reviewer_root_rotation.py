from truepanel.aegis.reliability import AegisReliabilityEngine
from truepanel.aegis.temperature_reviewer_root_rotation import (
    NAMESPACE,
    PREDECESSOR_KEY_ID,
    SUCCESSOR_KEY_ID,
    pending_temperature_reviewer_root_rotation,
)
from truepanel.holodeck.aegis_temperature_reviewer_root_rotation import (
    run_temperature_reviewer_root_rotation_checkride,
)


def test_rotation_has_dedicated_distinct_root_roles():
    assert "root-rotation" in NAMESPACE
    assert PREDECESSOR_KEY_ID != SUCCESSOR_KEY_ID


def test_pending_rotation_fails_closed():
    result = pending_temperature_reviewer_root_rotation({"status": "GOVERNED_REVIEWER_ROSTER_ACTIVE"})
    assert result["status"] == "ACTION_REQUIRED_DUAL_ROOT_ROTATION"
    assert result["rotation_authorized"] is False
    assert result["deployment_authority"] is False


def test_holodeck_requires_dual_signatures_and_monotonic_time():
    measurements = run_temperature_reviewer_root_rotation_checkride()["measurements"]
    assert measurements["scenario_count"] == 7
    assert measurements["trusted_count"] == 2
    assert measurements["hold_count"] == 5
    assert measurements["unsigned_transition_acceptances"] == 0
    assert measurements["generation_gap_acceptances"] == 0
    assert measurements["lead_samples"] == 27
    assert measurements["deployments"] == measurements["hardware_actions"] == 0


def test_mission_control_exposes_root_rotation_gate():
    result = AegisReliabilityEngine().observe({"timestamp": 0.0})["coverage_reviewer_root_rotation"]
    assert result["status"] == "HOLD"
    assert result["dual_control_verified"] is False


def test_mobile_copy_names_dual_control_boundary():
    with open("truepanel/web/static/reliability-view.js", encoding="utf-8") as stream:
        source = stream.read()
    assert "Reviewer Root Rotation" in source
    assert "Predecessor + successor signatures" in source
