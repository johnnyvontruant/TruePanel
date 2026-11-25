from truepanel.aegis.reliability import AegisReliabilityEngine
from truepanel.aegis.temperature_timestamp_trust_rotation import (
    STATUS_TRUSTED,
    pending_timestamp_trust_rotation,
)
from truepanel.holodeck.aegis_temperature_timestamp_trust_rotation import (
    run_temperature_timestamp_trust_rotation_checkride,
)


def test_pending_rotation_fails_closed():
    result = pending_timestamp_trust_rotation({"timestamp_trust_bundle_verified": True})
    assert result["status"] == "ACTION_REQUIRED_TIMESTAMP_TRUST_ROTATION"
    assert result["rotation_authorized"] is False
    assert result["deployment_authority"] is False


def test_checkride_requires_dual_control_and_revocation_archive():
    proof = run_temperature_timestamp_trust_rotation_checkride()
    measurements = proof["measurements"]
    assert measurements["scenario_count"] == 7
    assert measurements["trusted_rotations"] == 1
    assert measurements["hold_count"] == 6
    assert measurements["revocation_objects_archived"] == 2
    assert measurements["unsigned_transition_acceptances"] == 0
    assert measurements["stale_revocation_acceptances"] == 0
    assert measurements["lead_samples"] == 27
    assert sum(item["status"] == STATUS_TRUSTED for item in proof["scenarios"]) == 1


def test_reliability_exposes_rotation_gate():
    result = AegisReliabilityEngine().observe({"timestamp": 0.0})[
        "coverage_timestamp_trust_rotation"
    ]
    assert result["status"] == "HOLD"
    assert result["dual_control_verified"] is False
    assert result["revocation_evidence_verified"] == 0


def test_mobile_copy_discloses_dual_control_boundary():
    with open("truepanel/web/static/reliability-view.js", encoding="utf-8") as stream:
        source = stream.read()
    assert "Timestamp Trust Rotation" in source
    assert "archived revocation state" in source
