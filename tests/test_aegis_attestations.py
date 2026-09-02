from copy import deepcopy

from truepanel.aegis.attestations import (
    BACKUP_KIND,
    CANDIDATE_KIND,
    collect_recovery_attestations,
    issue_recovery_attestation,
    reconcile_recovery_attestations,
    validate_recovery_attestation,
)

INCIDENT_ID = "recovery:ground-truth-fixture"
NOW = 1_000.0


def payload():
    return {
        "timestamp": NOW,
        "backup_context": {
            "independent_backup_confirmed": True,
            "restore_tested": True,
            "verified_at": NOW - 30,
            "provider_id": "fixture.restore-verifier",
            "provider_mode": "deterministic_fixture",
            "evidence_sha256": "c" * 64,
            "evidence_reference": "fixture://restore/result-001",
            "evidence_maturity": "deterministic_lab_fixture",
            "restore_test_id": "restore-001",
            "scope": "critical-datasets",
        },
        "lifeline": {
            "sessions": [
                {
                    "status": "active",
                    "updated_at": NOW - 20,
                    "context": {
                        "replacement_candidates": [
                            {
                                "selected": True,
                                "model": "ST8000NE001",
                                "capacity_bytes": 8_000_000_000_000,
                                "member_of_pool": False,
                                "contains_preserved_data": False,
                                "identity_sha256": "b" * 64,
                                "provider_id": "fixture.passive-inventory",
                                "provider_mode": "deterministic_fixture",
                                "evidence_reference": "fixture://inventory/disk-001",
                                "evidence_maturity": "deterministic_lab_fixture",
                                "observed_at": NOW - 20,
                            }
                        ]
                    },
                    "last_session": {
                        "replacement": {
                            "valid": True,
                            "minimum_capacity_bytes": 8_000_000_000_000,
                        }
                    },
                }
            ]
        },
    }


def statements():
    return collect_recovery_attestations(
        payload(),
        incident_id=INCIDENT_ID,
        source_identity_sha256="a" * 64,
    )


def test_provider_boundary_emits_two_incident_bound_digest_statements():
    result = statements()

    assert [item["kind"] for item in result] == [BACKUP_KIND, CANDIDATE_KIND]
    assert all(item["incident_id"] == INCIDENT_ID for item in result)
    assert all(len(item["statement_sha256"]) == 64 for item in result)
    assert all(item["predicate"]["read_only"] is True for item in result)
    assert all(item["predicate"]["control_authority"] is False for item in result)
    assert all(
        item["predicate"]["cryptographic_authenticity"] is False
        for item in result
    )


def test_reconciler_accepts_complete_lab_evidence_without_overclaiming_trust():
    ledger = reconcile_recovery_attestations(
        statements(),
        incident_id=INCIDENT_ID,
        now=NOW,
    )

    assert ledger["status"] == "EVIDENCE_READY"
    assert len(ledger["accepted"]) == 2
    assert ledger["rejected"] == []
    assert ledger["missing_kinds"] == []
    assert ledger["evidence_maturity"] == "deterministic_lab_fixture"
    assert ledger["digest_authenticates_provider"] is False
    assert ledger["control_authority"] is False
    assert len(ledger["ledger_sha256"]) == 64


def test_mutation_incident_mismatch_and_expiry_are_rejected():
    cases = []

    mutated = statements()[0]
    mutated["predicate"]["claims"]["restore_tested"] = False
    cases.append((mutated, INCIDENT_ID, NOW, "attestation digest mismatch"))

    mismatch = statements()[0]
    cases.append((mismatch, "recovery:other", NOW, "incident binding mismatch"))

    expired = statements()[0]
    cases.append((expired, INCIDENT_ID, NOW + 901, "attestation has expired"))

    for statement, incident_id, now, expected in cases:
        assert expected in validate_recovery_attestation(
            statement,
            incident_id=incident_id,
            now=now,
        )


def test_weak_or_reused_candidate_identity_holds():
    weak_payload = payload()
    candidate = weak_payload["lifeline"]["sessions"][0]["context"][
        "replacement_candidates"
    ][0]
    candidate["identity_sha256"] = "a" * 64
    result = collect_recovery_attestations(
        weak_payload,
        incident_id=INCIDENT_ID,
        source_identity_sha256="a" * 64,
    )
    ledger = reconcile_recovery_attestations(
        result,
        incident_id=INCIDENT_ID,
        now=NOW,
    )

    assert ledger["status"] == "HOLD"
    assert CANDIDATE_KIND in ledger["missing_kinds"]
    assert any(
        "candidate identity is not strongly distinct" in item["errors"]
        for item in ledger["rejected"]
    )


def test_multiple_valid_attestations_of_one_kind_require_explicit_selection():
    result = statements()
    result.append(deepcopy(result[0]))
    ledger = reconcile_recovery_attestations(
        result,
        incident_id=INCIDENT_ID,
        now=NOW,
    )

    assert ledger["status"] == "HOLD"
    assert ledger["contradictions"] == [
        "multiple accepted backup.restore-verification attestations require explicit selection"
    ]


def test_untrusted_provider_mode_cannot_become_ready():
    statement = issue_recovery_attestation(
        kind=BACKUP_KIND,
        incident_id=INCIDENT_ID,
        provider_id="opaque.cloud",
        provider_mode="opaque_cloud",
        observed_at=NOW,
        subject_name="backup",
        subject_sha256="c" * 64,
        claims={
            "independent_backup_confirmed": True,
            "restore_tested": True,
            "restore_test_id": "restore-001",
            "scope": "critical-datasets",
        },
        evidence_reference="https://example.invalid/report",
        evidence_maturity="unknown",
    )

    assert "provider mode is not governed" in validate_recovery_attestation(
        statement,
        incident_id=INCIDENT_ID,
        now=NOW,
    )
