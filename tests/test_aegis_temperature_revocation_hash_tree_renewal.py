from truepanel.aegis.reliability import AegisReliabilityEngine
from truepanel.aegis.temperature_revocation_hash_tree_renewal import (
    STATUS_TRUSTED,
    pending_revocation_hash_tree_renewal,
)
from truepanel.holodeck.aegis_temperature_revocation_hash_tree_renewal import (
    run_temperature_revocation_hash_tree_renewal_checkride,
)


def test_pending_hash_tree_renewal_fails_closed():
    result = pending_revocation_hash_tree_renewal(
        {"status": "REVOCATION_ARCHIVE_RENEWAL_TRUSTED"}
    )
    assert result["status"] == "ACTION_REQUIRED_REVOCATION_HASH_TREE_RENEWAL"
    assert result["complete_archive_rehashed"] is False
    assert result["archive_timestamp_verified"] is False
    assert result["deployment_authority"] is False


def test_checkride_rehashes_complete_archive_and_rejects_downgrades():
    proof = run_temperature_revocation_hash_tree_renewal_checkride()
    measurements = proof["measurements"]
    assert measurements["scenario_count"] == 10
    assert measurements["trusted_renewals"] == 1
    assert measurements["hold_count"] == 9
    assert measurements["archive_objects_rehashed"] == 11
    assert measurements["inclusion_proofs_verified"] == 11
    assert measurements["actual_rfc3161_tokens_verified"] == 4
    assert measurements["digest_downgrade_acceptances"] == 0
    assert measurements["late_renewal_acceptances"] == 0
    assert measurements["coverage_gaps"] == 0
    assert measurements["lead_samples"] == 27
    assert sum(item["status"] == STATUS_TRUSTED for item in proof["scenarios"]) == 1


def test_reliability_exposes_hash_tree_renewal_gate():
    result = AegisReliabilityEngine().observe({"timestamp": 0.0})[
        "coverage_revocation_hash_tree_renewal"
    ]
    assert result["status"] == "HOLD"
    assert result["active_digest_algorithm"] == "sha512"
    assert result["eligible_for_timestamp_trust_rotation"] is False


def test_mobile_copy_discloses_digest_migration_and_profile_boundary():
    with open("truepanel/web/static/reliability-view.js", encoding="utf-8") as stream:
        source = stream.read()
    assert "Cryptographic Agility Renewal" in source
    assert "SHA-256 → SHA-512" in source
    assert "not RFC 4998 wire-compatible" in source
