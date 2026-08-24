from types import SimpleNamespace

from truepanel.guidance import guidance_for_snapshot
from truepanel.guidance.storage_evidence import StorageRecoveryEvidenceProvider
from truepanel.health import augment_status_snapshot


STATUS = """
  pool: HDDs
 state: DEGRADED
config:

        NAME          STATE     READ WRITE CKSUM
        HDDs          DEGRADED     0     0     0
          raidz1-0    DEGRADED     0     0     0
            /dev/sda2 ONLINE       0     0     0
            /dev/sdb2 ONLINE       0     0     0
            /dev/sdc2 FAULTED      8     0     2
            /dev/sdd2 ONLINE       0     0     0

errors: No known data errors
"""


class Inventory:
    def devices(self):
        return [
            SimpleNamespace(
                device="sdc",
                physical_bay=3,
                model="ST8000NE001",
                serial="WKD3MW4K",
                mapping_source="enclosure",
                enclosure="6:0:0:0",
                label="Front Bay 3",
                drive=SimpleNamespace(size_bytes=8_000_000_000_000),
            )
        ]


def test_drive_failure_flows_from_zfs_evidence_to_locked_recovery_guidance():
    provider = StorageRecoveryEvidenceProvider(
        inventory=Inventory(),
        runner=lambda: STATUS,
    )
    devices = provider.records()
    source = {
        "schema_version": 1,
        "read_only": True,
        "storage": {
            "pools": [{"name": "HDDs", "health": "DEGRADED"}],
            "devices": devices,
            "zfs_activity": {"resilver_running": False},
        },
    }

    guidance = guidance_for_snapshot(source)
    disk = next(
        item
        for item in guidance
        if item["code"] == "storage.disk_faulted"
    )
    gate = disk["runtime"]["action_gate"]
    evidence = disk["runtime"]["evidence"]

    assert evidence["pool"] == "HDDs"
    assert evidence["vdev"] == "raidz1-0"
    assert evidence["vdev_topology"] == "RAIDZ1"
    assert evidence["remaining_redundancy"] == 0
    assert evidence["device"] == "sdc"
    assert evidence["bay"] == 3
    assert evidence["zfs_state"] == "FAULTED"
    assert disk["runtime"]["phase"] == "prepare_repair"
    assert gate["safe_checks"] is True
    assert gate["physical_service_ready"] is False
    assert gate["destructive_actions_ready"] is False
    assert "backup_acknowledgement_required" in gate["blocked_by"]
    assert "replacement_candidate_not_validated" in gate["blocked_by"]

    augmented = augment_status_snapshot(source)
    assert augmented["storage"] is source["storage"]
    assert any(
        item["code"] == "storage.disk_faulted"
        for item in augmented["operator_guidance"]
    )


def test_resilver_changes_same_fault_into_monitor_recovery_phase():
    provider = StorageRecoveryEvidenceProvider(
        inventory=Inventory(),
        runner=lambda: STATUS,
    )
    source = {
        "storage": {
            "pools": [{"name": "HDDs", "health": "DEGRADED"}],
            "devices": provider.records(),
            "zfs_activity": {
                "resilver_running": True,
                "percent": 63,
                "remaining": "41m to go",
            },
        }
    }

    disk = next(
        item
        for item in guidance_for_snapshot(source)
        if item["code"] == "storage.disk_faulted"
    )

    assert disk["runtime"]["phase"] == "monitor_recovery"
    assert disk["runtime"]["evidence"]["resilver_state"]["percent"] == 63
    assert disk["runtime"]["action_gate"]["destructive_actions_ready"] is False
