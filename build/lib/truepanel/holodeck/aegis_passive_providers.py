"""Deterministic proof for passive TrueNAS recovery-evidence adapters."""

from __future__ import annotations

from typing import Any

from truepanel.aegis.attestations import (
    collect_recovery_attestations,
    reconcile_recovery_attestations,
)
from truepanel.aegis.passive_providers import (
    TrueNASProtectionEvidenceProvider,
    TrueNASReplacementInventoryProvider,
    issue_restore_verification_receipt,
)


class _Client:
    def __init__(self, responses: dict[str, list[dict[str, Any]]]) -> None:
        self.responses = responses

    def query(self, method: str, **_kwargs: Any) -> list[dict[str, Any]]:
        return [dict(item) for item in self.responses.get(method, [])]


class _CandidateDelegate:
    def candidates(self, *_args: Any, **_kwargs: Any) -> list[dict[str, Any]]:
        return [
            {
                "selected": True,
                "device": "sdh",
                "bay": 3,
                "model": "ST8000NE001",
                "serial_last4": "NEW1",
                "capacity_bytes": 8_000_000_000_000,
                "member_of_pool": False,
                "contains_preserved_data": False,
                "identity_verified_distinct": True,
                "observed_at": 990.0,
            }
        ]


def _responses(*, pool: str | None = None, serial: str = "ZCTNEW1"):
    return {
        "replication.query": [
            {
                "id": 7,
                "name": "offsite",
                "enabled": True,
                "source_datasets": ["HDDs/media"],
                "state": {"state": "SUCCESS"},
            }
        ],
        "cloud_backup.query": [],
        "disk.query": [
            {
                "identifier": "{serial}ZCTNEW1",
                "name": "sdh",
                "serial": serial,
                "model": "ST8000NE001",
                "size": 8_000_000_000_000,
                "pool": pool,
            }
        ],
    }


def _ledger(*, receipt=True, pool=None, serial="ZCTNEW1") -> dict[str, Any]:
    incident_id = "recovery:fixture"
    responses = _responses(pool=pool, serial=serial)
    client = _Client(responses)
    restore_receipt = issue_restore_verification_receipt(
        incident_id=incident_id,
        method="replication.query",
        task_id=7,
        scope="HDDs/media",
        restore_test_id="restore-42",
        verified_at=990.0,
        objects_verified=12,
    )
    protection = TrueNASProtectionEvidenceProvider(
        client,
        receipt_loader=(lambda: restore_receipt) if receipt else None,
    ).observe(incident_id=incident_id)
    candidates = TrueNASReplacementInventoryProvider(
        client, _CandidateDelegate()
    ).candidates({})
    payload = {
        "timestamp": 1_000.0,
        "backup_context": protection.get("backup_context", {}),
        "lifeline": {
            "sessions": [
                {
                    "status": "active",
                    "updated_at": 990.0,
                    "context": {"replacement_candidates": candidates},
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
    statements = collect_recovery_attestations(
        payload,
        incident_id=incident_id,
        source_identity_sha256="a" * 64,
    )
    return reconcile_recovery_attestations(
        statements,
        incident_id=incident_id,
        now=1_000.0,
    )


def run_passive_provider_rehearsal() -> dict[str, Any]:
    positive = _ledger()
    negatives = [
        {"scenario": "task_success_without_restore_test", "ledger": _ledger(receipt=False)},
        {"scenario": "candidate_already_in_pool", "ledger": _ledger(pool="HDDs")},
        {"scenario": "disk_identity_mismatch", "ledger": _ledger(serial="DIFFERENT")},
    ]
    false_ready = sum(
        1 for item in negatives if item["ledger"]["status"] == "EVIDENCE_READY"
    )
    return {
        "schema_version": 1,
        "scenario": "truenas-passive-recovery-providers-v1",
        "hardware_isolated": True,
        "field_validated": False,
        "control_authority": False,
        "positive_ledger": positive,
        "negative_scenarios": negatives,
        "measurements": {
            "documented_query_methods": 3,
            "mutating_methods": 0,
            "positive_statements_accepted": len(positive["accepted"]),
            "negative_holds": sum(
                1 for item in negatives if item["ledger"]["status"] == "HOLD"
            ),
            "unsafe_false_ready": false_ready,
            "task_success_promoted_without_restore_test": False,
        },
    }


__all__ = ["run_passive_provider_rehearsal"]
