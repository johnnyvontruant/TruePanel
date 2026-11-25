from truepanel.aegis.reliability import AegisReliabilityEngine
from truepanel.aegis.temperature_rfc4998_interop_fixture import (
    STATUS_SELF_VERIFIED,
    pending_rfc4998_interoperability_fixture,
)
from truepanel.holodeck.aegis_temperature_rfc4998_interop_fixture import (
    run_temperature_rfc4998_interop_checkride,
)


def test_pending_interoperability_gate_fails_closed():
    result = pending_rfc4998_interoperability_fixture(
        {"status": "REVOCATION_HASH_TREE_RENEWAL_TRUSTED"}
    )
    assert result["status"] == "ACTION_REQUIRED_RFC4998_INTEROPERABILITY_FIXTURE"
    assert result["external_interoperability_validation"] == "PENDING"
    assert result["eligible_for_timestamp_trust_rotation"] is False
    assert result["deployment_authority"] is False


def test_checkride_exports_strict_detached_profile_and_holds_adversarial_inputs():
    proof = run_temperature_rfc4998_interop_checkride()
    measurements = proof["measurements"]
    assert measurements["scenario_count"] == 8
    assert measurements["self_verified_fixtures"] == 1
    assert measurements["external_validation_ready"] == 1
    assert measurements["external_validations_completed"] == 0
    assert measurements["hold_count"] == 7
    assert measurements["actual_rfc3161_content_info_tokens_verified"] == 1
    assert measurements["wrong_root_acceptances"] == 0
    assert measurements["malformed_der_acceptances"] == 0
    assert measurements["digest_downgrade_acceptances"] == 0
    assert measurements["untrusted_tsa_acceptances"] == 0
    assert measurements["lead_samples"] == 27
    assert (
        sum(item["status"] == STATUS_SELF_VERIFIED for item in proof["scenarios"]) == 1
    )


def test_reliability_exposes_external_interoperability_gate():
    result = AegisReliabilityEngine().observe({"timestamp": 0.0})[
        "coverage_rfc4998_interoperability"
    ]
    assert result["status"] == "HOLD"
    assert result["external_interoperability_validation"] == "PENDING"
    assert result["eligible_for_external_interoperability_validation"] is False


def test_mobile_copy_does_not_overstate_interoperability():
    with open("truepanel/web/static/reliability-view.js", encoding="utf-8") as stream:
        source = stream.read()
    assert "RFC 4998 Interoperability Gate" in source
    assert "ETSI DSS / Bouncy Castle validation" in source
    assert "Self-verification is an export gate" in source
