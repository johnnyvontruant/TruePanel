import json
from types import SimpleNamespace

import pytest

from truepanel.aegis.passive_providers import (
    TrueNASProtectionEvidenceProvider,
    TrueNASReadOnlyQueryClient,
    TrueNASReplacementInventoryProvider,
    issue_restore_verification_receipt,
)


class FakeClient:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def query(self, method, **kwargs):
        self.calls.append((method, kwargs))
        return self.responses.get(method, [])


def test_query_client_allows_only_documented_read_methods():
    calls = []

    def runner(command, **kwargs):
        calls.append((command, kwargs))
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps([{"identifier": "disk-1"}]),
        )

    client = TrueNASReadOnlyQueryClient(runner=runner, executable="/usr/bin/midclt")
    assert client.query("disk.query", options={"extra": {"pools": True}}) == [
        {"identifier": "disk-1"}
    ]
    assert calls[0][0][:3] == ["/usr/bin/midclt", "call", "disk.query"]
    assert json.loads(calls[0][0][4]) == {"extra": {"pools": True}}
    assert calls[0][1]["timeout"] == 10.0

    with pytest.raises(ValueError, match="not read-only allowlisted"):
        client.query("disk.wipe")


@pytest.mark.parametrize("state", ["SUCCESS", "FINISHED"])
def test_successful_task_without_restore_receipt_remains_unverified(state):
    client = FakeClient(
        {
            "replication.query": [
                {
                    "id": 7,
                    "name": "offsite",
                    "enabled": True,
                    "source_datasets": ["HDDs/media"],
                    "state": {"state": state},
                }
            ]
        }
    )
    result = TrueNASProtectionEvidenceProvider(client).observe(incident_id="inc-1")
    assert result["successful_tasks"] == 1
    assert result["restore_verified"] is False
    assert "not a tested restore" in result["hold_reason"]
    assert "backup_context" not in result
    assert result["control_authority"] is False


@pytest.mark.parametrize("state", ["FAILED", "ABORTED", "RUNNING", "WAITING", "UNKNOWN"])
def test_non_successful_task_states_remain_unqualified(state):
    client = FakeClient(
        {
            "replication.query": [
                {
                    "id": 7,
                    "name": "offsite",
                    "enabled": True,
                    "source_datasets": ["HDDs/media"],
                    "state": {"state": state},
                }
            ]
        }
    )
    result = TrueNASProtectionEvidenceProvider(client).observe(incident_id="inc-1")
    assert result["successful_tasks"] == 0
    assert result["restore_verified"] is False
    assert "backup_context" not in result


def test_matching_digest_intact_restore_receipt_promotes_finished_task():
    receipt = issue_restore_verification_receipt(
        incident_id="inc-1",
        method="replication.query",
        task_id=7,
        scope="HDDs/media",
        restore_test_id="restore-42",
        verified_at=990.0,
        objects_verified=12,
    )
    client = FakeClient(
        {
            "replication.query": [
                {
                    "id": 7,
                    "name": "offsite",
                    "enabled": True,
                    "source_datasets": ["HDDs/media"],
                    "state": {"state": "FINISHED"},
                }
            ]
        }
    )
    result = TrueNASProtectionEvidenceProvider(
        client, receipt_loader=lambda: receipt
    ).observe(incident_id="inc-1")
    backup = result["backup_context"]
    assert result["restore_verified"] is True
    assert backup["restore_tested"] is True
    assert backup["provider_id"] == "truenas-api:restore-verification"
    assert backup["evidence_sha256"] == receipt["evidence_sha256"]


@pytest.mark.parametrize("mutation", ["incident", "digest", "result", "objects"])
def test_invalid_restore_receipts_fail_closed(mutation):
    receipt = issue_restore_verification_receipt(
        incident_id="inc-1",
        method="cloud_backup.query",
        task_id=9,
        scope="/mnt/HDDs",
        restore_test_id="restore-9",
        verified_at=990.0,
        objects_verified=3,
    )
    if mutation == "incident":
        receipt["incident_id"] = "wrong"
    elif mutation == "digest":
        receipt["scope"] = "tampered"
    elif mutation == "result":
        receipt["result"] = "FAIL"
    else:
        receipt["objects_verified"] = 0
    client = FakeClient(
        {
            "cloud_backup.query": [
                {
                    "id": 9,
                    "enabled": True,
                    "path": "/mnt/HDDs",
                    "job": {"state": "SUCCESS"},
                }
            ]
        }
    )
    result = TrueNASProtectionEvidenceProvider(
        client, receipt_loader=lambda: receipt
    ).observe(incident_id="inc-1")
    assert result["restore_verified"] is False
    assert "backup_context" not in result


def test_restore_receipt_scope_must_match_the_successful_task():
    receipt = issue_restore_verification_receipt(
        incident_id="inc-1",
        method="replication.query",
        task_id=7,
        scope="HDDs/wrong",
        restore_test_id="restore-42",
        verified_at=990.0,
        objects_verified=12,
    )
    client = FakeClient(
        {
            "replication.query": [
                {
                    "id": 7,
                    "enabled": True,
                    "source_datasets": ["HDDs/media"],
                    "state": {"state": "SUCCESS"},
                }
            ]
        }
    )
    result = TrueNASProtectionEvidenceProvider(
        client, receipt_loader=lambda: receipt
    ).observe(incident_id="inc-1")
    assert result["restore_verified"] is False
    assert result["hold_reason"] == "restore verification receipt is invalid"


def test_disk_query_must_cross_check_local_candidate_before_attestation():
    candidate = {
        "device": "sdh",
        "model": "ST8000NE001",
        "serial_last4": "NEW1",
        "capacity_bytes": 8_000_000_000_000,
        "member_of_pool": False,
        "contains_preserved_data": False,
    }

    class Delegate:
        def candidates(self, *_args, **_kwargs):
            return [candidate]

    api = {
        "identifier": "{serial}ZCTNEW1",
        "name": "sdh",
        "serial": "ZCTNEW1",
        "model": "ST8000NE001",
        "size": 8_000_000_000_000,
        "pool": None,
    }
    client = FakeClient({"disk.query": [api]})
    provider = TrueNASReplacementInventoryProvider(client, Delegate())
    result = provider.candidates({}, storage_devices=[])
    assert len(result) == 1
    assert result[0]["provider_id"] == "truenas-api:disk.query"
    assert len(result[0]["identity_sha256"]) == 64
    assert client.calls[0][1] == {"options": {"extra": {"pools": True}}}

    api["pool"] = "HDDs"
    assert provider.candidates({}, storage_devices=[]) == []


@pytest.mark.parametrize(
    ("serial", "size", "model"),
    [
        ("DIFFERENT", 8_000, "ST8000NE001"),
        ("ZCTNEW1", 4_000, "ST8000NE001"),
        ("ZCTNEW1", 8_000, "OTHER"),
    ],
)
def test_disk_query_identity_or_capacity_mismatch_fails_closed(
    serial, size, model
):
    class Delegate:
        def candidates(self, *_args, **_kwargs):
            return [
                {
                    "device": "sdh",
                    "model": "ST8000NE001",
                    "serial_last4": "NEW1",
                    "capacity_bytes": 8_000,
                    "member_of_pool": False,
                    "contains_preserved_data": False,
                }
            ]

    client = FakeClient(
        {
            "disk.query": [
                {
                    "identifier": "disk-1",
                    "name": "sdh",
                    "serial": serial,
                    "size": size,
                    "model": model,
                    "pool": None,
                }
            ]
        }
    )
    assert TrueNASReplacementInventoryProvider(client, Delegate()).candidates({}) == []
