from __future__ import annotations

from truepanel.health import augment_status_snapshot


def test_faulted_drive_publishes_lifeline_backed_checklist() -> None:
    source = {
        "schema_version": 1,
        "read_only": True,
        "storage": {
            "pools": [{"name": "HDDs", "health": "DEGRADED"}],
            "devices": [
                {
                    "pool": "HDDs",
                    "vdev": "raidz1-0",
                    "vdev_topology": "RAIDZ1",
                    "remaining_redundancy": 0,
                    "member_id": "disk-guid-4",
                    "physical_bay": 4,
                    "device": "sdc",
                    "model": "ST8000NE001",
                    "capacity_bytes": 8_000_000_000_000,
                    "present": True,
                    "zfs_state": "FAULTED",
                    "read_errors": 8,
                    "write_errors": 0,
                    "checksum_errors": 2,
                }
            ],
        },
        "lifeline": {
            "service_procedure_verified": False,
            "bay_identity_verified": True,
            "acknowledgements": {
                "backup_state": False,
                "replacement_operation": False,
            },
        },
    }

    augmented = augment_status_snapshot(source)
    checklist = next(
        item
        for item in augmented["operator_checklists"]
        if item["code"] == "storage.disk_faulted"
    )
    preflight = {item["key"]: item for item in checklist["preflight"]}

    assert "operator_checklists" not in source
    assert checklist["read_only"] is True
    assert checklist["target"]["pool"] == "HDDs"
    assert checklist["target"]["bay"] == 4
    assert checklist["capabilities"]["can_identify_bay"] is True
    assert checklist["capabilities"]["can_execute_replacement"] is False
    assert preflight["member_identity"]["state"] == "verified"
    assert preflight["physical_identity"]["state"] == "verified"
    assert preflight["service_procedure"]["state"] == "hold"
    assert preflight["backup_acknowledgement"]["state"] == "hold"
    assert checklist["status"] == "hold"


def test_network_fault_publishes_generic_pending_checklist() -> None:
    source = {
        "network": [
            {
                "name": "enp116s0",
                "label": "Primary LAN",
                "primary": True,
                "link_up": False,
                "operstate": "down",
            }
        ]
    }

    augmented = augment_status_snapshot(source)
    checklist = next(
        item
        for item in augmented["operator_checklists"]
        if item["code"] == "network.link_down"
    )

    assert checklist["preflight"] == []
    assert checklist["phase"] == "diagnose"
    assert checklist["sections"]
    assert all(
        step["state"] == "pending"
        for section in checklist["sections"]
        for step in section["steps"]
    )
