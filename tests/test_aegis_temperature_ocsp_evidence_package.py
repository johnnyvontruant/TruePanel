from truepanel.aegis.reliability import AegisReliabilityEngine
from truepanel.aegis.temperature_ocsp_evidence_package import (
    STATUS_TRUSTED,
    pending_ocsp_evidence_package,
)
from truepanel.holodeck.aegis_temperature_ocsp_evidence_package import (
    run_temperature_ocsp_evidence_package_checkride,
)


def test_pending_ocsp_package_fails_closed():
    result = pending_ocsp_evidence_package(
        {"eligible_for_timestamp_trust_rotation": True}
    )
    assert result["status"] == "ACTION_REQUIRED_OCSP_EVIDENCE_PACKAGE"
    assert result["eligible_for_timestamp_trust_rotation"] is False
    assert result["responder_authorized"] is False
    assert result["deployment_authority"] is False


def test_checkride_binds_ocsp_status_responder_and_archive_timestamp():
    proof = run_temperature_ocsp_evidence_package_checkride()
    measurements = proof["measurements"]
    assert measurements["scenario_count"] == 9
    assert measurements["trusted_packages"] == 1
    assert measurements["hold_count"] == 8
    assert measurements["actual_der_ocsp_responses_parsed"] == 5
    assert measurements["authorized_responders_verified"] == 1
    assert measurements["actual_rfc3161_tokens_verified"] == 1
    assert measurements["serial_bindings_verified"] == 1
    assert measurements["revoked_status_acceptances"] == 0
    assert measurements["unauthorized_responder_acceptances"] == 0
    assert measurements["wrong_certificate_acceptances"] == 0
    assert measurements["lead_samples"] == 27
    assert sum(item["status"] == STATUS_TRUSTED for item in proof["scenarios"]) == 1


def test_reliability_exposes_ocsp_evidence_gate():
    result = AegisReliabilityEngine().observe({"timestamp": 0.0})[
        "coverage_ocsp_evidence_package"
    ]
    assert result["status"] == "HOLD"
    assert result["der_ocsp_verified"] is False
    assert result["responder_authorized"] is False


def test_mobile_copy_discloses_ocsp_authorization_boundary():
    with open("truepanel/web/static/reliability-view.js", encoding="utf-8") as stream:
        source = stream.read()
    assert "OCSP Evidence Archive" in source
    assert "authorized responder" in source
    assert "exact certificate identity" in source
