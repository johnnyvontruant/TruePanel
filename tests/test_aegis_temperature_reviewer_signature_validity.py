from truepanel.aegis.reliability import AegisReliabilityEngine
from truepanel.aegis.temperature_reviewer_signature_validity import (
    STATUS_COMPROMISED,
    STATUS_PRECOMPROMISE,
    pending_temperature_reviewer_signature_validity,
)
from truepanel.holodeck.aegis_temperature_reviewer_signature_validity import (
    run_temperature_reviewer_signature_validity_checkride,
)


def test_statuses_distinguish_pre_and_post_compromise():
    assert STATUS_PRECOMPROMISE != STATUS_COMPROMISED


def test_pending_gate_fails_closed():
    result = pending_temperature_reviewer_signature_validity(
        {"dual_control_verified": True}
    )
    assert result["status"] == "ACTION_REQUIRED_HISTORICAL_SIGNATURE_VALIDITY"
    assert result["eligible_for_reviewer_quorum"] is False
    assert result["deployment_authority"] is False


def test_holodeck_enforces_compromise_time():
    measurements = run_temperature_reviewer_signature_validity_checkride()[
        "measurements"
    ]
    assert measurements["scenario_count"] == 6
    assert measurements["precompromise_valid_count"] == 1
    assert measurements["unaffected_valid_count"] == 1
    assert measurements["compromised_hold_count"] == 2
    assert measurements["untrusted_rotation_acceptances"] == 0
    assert measurements["authority_escalation_acceptances"] == 0
    assert measurements["lead_samples"] == 27


def test_mission_control_exposes_temporal_gate():
    result = AegisReliabilityEngine().observe({"timestamp": 0.0})[
        "coverage_reviewer_signature_validity"
    ]
    assert result["status"] == "HOLD"
    assert result["historical_signature_accepted"] is False


def test_mobile_copy_explains_crypto_is_not_enough():
    with open("truepanel/web/static/reliability-view.js", encoding="utf-8") as stream:
        source = stream.read()
    assert "Historical Reviewer Signature" in source
    assert "created at or after compromise remains HOLD" in source
