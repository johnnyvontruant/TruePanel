from truepanel.aegis.reliability import AegisReliabilityEngine
from truepanel.aegis.temperature_reviewer_timestamp_witness import (
    STATUS_COMPROMISED,
    STATUS_PRECOMPROMISE,
    pending_temperature_reviewer_timestamp_witness,
)
from truepanel.holodeck.aegis_temperature_reviewer_timestamp_witness import (
    run_temperature_reviewer_timestamp_witness_checkride,
)


def test_statuses_distinguish_witnessed_pre_and_post_compromise():
    assert STATUS_PRECOMPROMISE != STATUS_COMPROMISED


def test_pending_timestamp_witness_fails_closed():
    result = pending_temperature_reviewer_timestamp_witness(
        {"root_rotation_verified": True, "reviewer_signature_verified": True}
    )
    assert result["status"] == "ACTION_REQUIRED_RFC3161_TIMESTAMP_WITNESS"
    assert result["timestamp_witness_verified"] is False
    assert result["eligible_for_reviewer_quorum"] is False
    assert result["deployment_authority"] is False


def test_holodeck_enforces_independent_timestamp_evidence():
    measurements = run_temperature_reviewer_timestamp_witness_checkride()[
        "measurements"
    ]
    assert measurements["scenario_count"] == 7
    assert measurements["precompromise_valid_count"] == 1
    assert measurements["unaffected_valid_count"] == 1
    assert measurements["postcompromise_hold_count"] == 1
    assert measurements["tampered_token_acceptances"] == 0
    assert measurements["delayed_witness_acceptances"] == 0
    assert measurements["untrusted_rotation_acceptances"] == 0
    assert measurements["authority_escalation_acceptances"] == 0
    assert measurements["lead_samples"] == 27


def test_mission_control_exposes_timestamp_gate():
    result = AegisReliabilityEngine().observe({"timestamp": 0.0})[
        "coverage_reviewer_timestamp_witness"
    ]
    assert result["status"] == "HOLD"
    assert result["timestamp_witness_verified"] is False
    assert result["historical_signature_accepted"] is False


def test_mobile_copy_discloses_independent_time_boundary():
    with open("truepanel/web/static/reliability-view.js", encoding="utf-8") as stream:
        source = stream.read()
    assert "Independent Timestamp Witness" in source
    assert "Signer-asserted time never substitutes" in source
