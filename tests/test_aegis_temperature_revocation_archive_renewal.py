from truepanel.aegis.reliability import AegisReliabilityEngine
from truepanel.aegis.temperature_revocation_archive_renewal import (
    STATUS_TRUSTED,
    pending_revocation_archive_renewal,
)
from truepanel.holodeck.aegis_temperature_revocation_archive_renewal import (
    run_temperature_revocation_archive_renewal_checkride,
)


def test_pending_archive_renewal_fails_closed():
    result = pending_revocation_archive_renewal(
        {"eligible_for_timestamp_trust_rotation": True}
    )
    assert result["status"] == "ACTION_REQUIRED_REVOCATION_ARCHIVE_RENEWAL"
    assert result["predecessor_packages_verified"] is False
    assert result["crl_and_ocsp_bound"] is False
    assert result["deployment_authority"] is False


def test_checkride_binds_both_evidence_packages_and_prior_timestamps():
    proof = run_temperature_revocation_archive_renewal_checkride()
    measurements = proof["measurements"]
    assert measurements["scenario_count"] == 10
    assert measurements["trusted_renewals"] == 1
    assert measurements["hold_count"] == 9
    assert measurements["crl_and_ocsp_packages_reverified"] == 2
    assert measurements["prior_archive_timestamps_bound"] == 2
    assert measurements["actual_rfc3161_tokens_verified"] == 3
    assert measurements["generation_advances_verified"] == 1
    assert measurements["identity_mismatch_acceptances"] == 0
    assert measurements["tampered_predecessor_acceptances"] == 0
    assert measurements["late_renewal_acceptances"] == 0
    assert measurements["lead_samples"] == 27
    assert sum(item["status"] == STATUS_TRUSTED for item in proof["scenarios"]) == 1


def test_reliability_exposes_archive_renewal_gate():
    result = AegisReliabilityEngine().observe({"timestamp": 0.0})[
        "coverage_revocation_archive_renewal"
    ]
    assert result["status"] == "HOLD"
    assert result["predecessor_packages_verified"] is False
    assert result["archive_timestamp_verified"] is False


def test_mobile_copy_discloses_renewal_profile_and_authority_boundary():
    with open("truepanel/web/static/reliability-view.js", encoding="utf-8") as stream:
        source = stream.read()
    assert "Revocation Archive Renewal" in source
    assert "earliest deadline" in source
    assert "not represented as RFC 4998 wire-compatible" in source
