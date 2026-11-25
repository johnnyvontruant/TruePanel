from truepanel.aegis.reliability import AegisReliabilityEngine
from truepanel.aegis.temperature_revocation_evidence_package import (
    STATUS_TRUSTED,
    pending_revocation_evidence_package,
)
from truepanel.holodeck.aegis_temperature_revocation_evidence_package import (
    run_temperature_revocation_evidence_package_checkride,
)


def test_pending_revocation_package_fails_closed():
    result = pending_revocation_evidence_package({"rotation_authorized": True})
    assert result["status"] == "ACTION_REQUIRED_REVOCATION_EVIDENCE_PACKAGE"
    assert result["eligible_for_timestamp_trust_rotation"] is False
    assert result["deployment_authority"] is False


def test_checkride_binds_der_crl_serial_and_archive_timestamp():
    proof = run_temperature_revocation_evidence_package_checkride()
    measurements = proof["measurements"]
    assert measurements["scenario_count"] == 8
    assert measurements["trusted_packages"] == 1
    assert measurements["hold_count"] == 7
    assert measurements["actual_der_crls_parsed"] == 3
    assert measurements["actual_rfc3161_tokens_verified"] == 1
    assert measurements["serial_bindings_verified"] == 1
    assert measurements["revoked_certificate_acceptances"] == 0
    assert measurements["expired_renewal_acceptances"] == 0
    assert measurements["lead_samples"] == 27
    assert sum(item["status"] == STATUS_TRUSTED for item in proof["scenarios"]) == 1


def test_reliability_exposes_revocation_evidence_gate():
    result = AegisReliabilityEngine().observe({"timestamp": 0.0})[
        "coverage_revocation_evidence_package"
    ]
    assert result["status"] == "HOLD"
    assert result["der_crl_verified"] is False
    assert result["archive_timestamp_verified"] is False


def test_mobile_copy_discloses_archive_boundary():
    with open("truepanel/web/static/reliability-view.js", encoding="utf-8") as stream:
        source = stream.read()
    assert "Revocation Evidence Archive" in source
    assert "Exact DER CRL" in source
    assert "post-expiry timestamp never substitutes" in source
