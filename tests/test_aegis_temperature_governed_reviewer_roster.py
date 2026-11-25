from truepanel.aegis.reliability import AegisReliabilityEngine
from truepanel.aegis.temperature_governed_reviewer_roster import (
    GOVERNANCE_KEY_ID,
    NAMESPACE,
    pending_temperature_governed_reviewer_roster,
)
from truepanel.holodeck.aegis_temperature_governed_reviewer_roster import (
    run_temperature_governed_reviewer_roster_checkride,
)


def test_roster_has_dedicated_root_and_namespace():
    assert GOVERNANCE_KEY_ID == "reviewer-roster-governance-root"
    assert "reviewer-roster" in NAMESPACE


def test_pending_roster_fails_closed():
    result = pending_temperature_governed_reviewer_roster({"primary_review_present": True})
    assert result["status"] == "ACTION_REQUIRED_GOVERNED_REVIEWER_ROSTER"
    assert result["reviewer_quorum_authorized"] is False
    assert result["deployment_authority"] is False


def test_holodeck_rehearses_rotation_revocation_and_expiry():
    measurements = run_temperature_governed_reviewer_roster_checkride()["measurements"]
    assert measurements["scenario_count"] == 6
    assert measurements["active_count"] == 2
    assert measurements["hold_count"] == 4
    assert measurements["revoked_acceptances"] == 0
    assert measurements["duplicate_identity_acceptances"] == 0
    assert measurements["lead_samples"] == 27
    assert measurements["deployments"] == measurements["hardware_actions"] == 0


def test_mission_control_exposes_governance_gate():
    payload = AegisReliabilityEngine().observe({"timestamp": 0.0})
    roster = payload["coverage_governed_reviewer_roster"]
    assert roster["status"] == "HOLD"
    assert roster["reviewer_quorum_authorized"] is False


def test_mobile_copy_names_roster_boundaries():
    with open("truepanel/web/static/reliability-view.js", encoding="utf-8") as stream:
        source = stream.read()
    assert "Governed Reviewer Roster" in source
    assert "revocation · rotation" in source
