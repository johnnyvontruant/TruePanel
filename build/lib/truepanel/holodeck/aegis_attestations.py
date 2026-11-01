"""Hardware-isolated HoloDeck rehearsal for AEGIS recovery attestations."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from truepanel.aegis.attestations import (
    collect_recovery_attestations,
    reconcile_recovery_attestations,
)

INCIDENT_ID = "recovery:holodeck-ground-truth"
NOW = 10_000.0


def _payload() -> dict[str, Any]:
    return {
        "timestamp": NOW,
        "backup_context": {
            "independent_backup_confirmed": True,
            "restore_tested": True,
            "verified_at": NOW - 30,
            "provider_id": "holodeck.restore-verifier",
            "provider_mode": "deterministic_fixture",
            "evidence_sha256": "c" * 64,
            "evidence_reference": "holodeck://restore/result-001",
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
                                "provider_id": "holodeck.passive-inventory",
                                "provider_mode": "deterministic_fixture",
                                "evidence_reference": "holodeck://inventory/disk-001",
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


def _collect(payload: dict[str, Any], *, source_digest: str = "a" * 64):
    return collect_recovery_attestations(
        payload,
        incident_id=INCIDENT_ID,
        source_identity_sha256=source_digest,
    )


def _case(name: str, statements: list[dict[str, Any]], now: float) -> dict[str, Any]:
    ledger = reconcile_recovery_attestations(
        statements,
        incident_id=INCIDENT_ID,
        now=now,
    )
    return {
        "name": name,
        "status": ledger["status"],
        "accepted": len(ledger["accepted"]),
        "rejected": len(ledger["rejected"]),
        "missing_kinds": ledger["missing_kinds"],
        "contradictions": ledger["contradictions"],
        "rejection_reasons": [
            reason
            for item in ledger["rejected"]
            for reason in item["errors"]
        ],
        "ledger_sha256": ledger["ledger_sha256"],
        "control_authority": ledger["control_authority"],
    }


def run_recovery_attestation_rehearsal() -> dict[str, Any]:
    """Rehearse one valid path and six fail-closed paths."""

    good = _collect(_payload())
    cases = [_case("fresh-bound-evidence", good, NOW)]

    mutated = deepcopy(good)
    mutated[0]["predicate"]["claims"]["restore_tested"] = False
    cases.append(_case("mutated-statement", mutated, NOW))
    cases.append(_case("expired-evidence", deepcopy(good), NOW + 901))

    reused_payload = _payload()
    candidate = reused_payload["lifeline"]["sessions"][0]["context"][
        "replacement_candidates"
    ][0]
    candidate["identity_sha256"] = "a" * 64
    cases.append(_case("reused-drive-identity", _collect(reused_payload), NOW))

    untrusted_payload = _payload()
    untrusted_payload["backup_context"]["provider_mode"] = "opaque_cloud"
    cases.append(_case("ungoverned-provider", _collect(untrusted_payload), NOW))

    cases.append(_case("missing-backup", deepcopy(good[1:]), NOW))
    duplicate = deepcopy(good)
    duplicate.append(deepcopy(good[0]))
    cases.append(_case("ambiguous-duplicate", duplicate, NOW))

    unsafe = [item for item in cases[1:] if item["status"] == "EVIDENCE_READY"]
    return {
        "scenario": "aegis-recovery-ground-truth-v1",
        "hardware_isolated": True,
        "field_validated": False,
        "evidence_maturity": "deterministic_lab_fixture",
        "cases": cases,
        "measurements": {
            "cases": len(cases),
            "positive_ready": sum(
                item["status"] == "EVIDENCE_READY" for item in cases[:1]
            ),
            "negative_holds": sum(item["status"] == "HOLD" for item in cases[1:]),
            "unsafe_false_ready": len(unsafe),
            "positive_attestations_accepted": cases[0]["accepted"],
        },
        "control_authority": False,
    }


__all__ = ["run_recovery_attestation_rehearsal"]
