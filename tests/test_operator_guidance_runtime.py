from truepanel.guidance import guidance_for_snapshot
from truepanel.health import augment_status_snapshot


def guidance_codes(payload):
    return [item["code"] for item in guidance_for_snapshot(payload)]


def test_healthy_and_unknown_pool_states_do_not_raise_repair_guidance():
    healthy = {
        "storage": {
            "pools": [
                {"name": "HDDs", "health": "ONLINE"},
                {"name": "SSDs", "health": "UNKNOWN"},
            ]
        }
    }

    assert guidance_for_snapshot(healthy) == []


def test_degraded_pool_routes_to_diagnosis_without_guessing_failed_disk():
    payload = {
        "storage": {
            "pools": [
                {"name": "HDDs", "health": "DEGRADED"},
            ]
        }
    }

    guidance = guidance_for_snapshot(payload)

    assert [item["code"] for item in guidance] == ["storage.pool_degraded"]
    runtime = guidance[0]["runtime"]
    assert runtime["phase"] == "diagnose"
    assert runtime["evidence"]["pool"] == "HDDs"
    assert runtime["evidence"]["pool_state"] == "DEGRADED"
    assert runtime["action_gate"]["safe_checks"] is True
    assert runtime["action_gate"]["physical_service_ready"] is False
    assert runtime["action_gate"]["destructive_actions_ready"] is False
    assert "physical_bay_not_identified" in runtime["action_gate"]["blocked_by"]
    assert "storage.disk_faulted" not in guidance_codes(payload)


def test_smart_warning_does_not_become_zfs_disk_fault():
    payload = {
        "storage": {
            "pools": [{"name": "HDDs", "health": "ONLINE"}],
            "smart": [
                {
                    "drive": "sdc",
                    "health": "PASSED",
                    "pending": 2,
                    "critical_warning": "0x00",
                }
            ],
        }
    }

    guidance = guidance_for_snapshot(payload)

    assert [item["code"] for item in guidance] == ["storage.smart_warning"]
    runtime = guidance[0]["runtime"]
    assert runtime["evidence"]["device"] == "sdc"
    assert runtime["evidence"]["pending"] == 2
    assert "zfs_membership_not_verified" in runtime["action_gate"]["blocked_by"]
    assert runtime["action_gate"]["destructive_actions_ready"] is False


def test_faulted_member_requires_exact_evidence_but_never_unlocks_destructive_action():
    payload = {
        "storage": {
            "pools": [{"name": "HDDs", "health": "DEGRADED"}],
            "devices": [
                {
                    "pool": "HDDs",
                    "vdev": "raidz1-0",
                    "vdev_topology": "RAIDZ1",
                    "remaining_redundancy": 0,
                    "physical_bay": 3,
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
        }
    }

    guidance = guidance_for_snapshot(payload)
    disk = next(item for item in guidance if item["code"] == "storage.disk_faulted")
    runtime = disk["runtime"]

    assert runtime["phase"] == "prepare_repair"
    assert runtime["evidence"]["pool"] == "HDDs"
    assert runtime["evidence"]["vdev"] == "raidz1-0"
    assert runtime["evidence"]["bay"] == 3
    assert runtime["evidence"]["device"] == "sdc"
    assert runtime["evidence"]["remaining_redundancy"] == 0
    assert runtime["action_gate"]["physical_service_ready"] is False
    assert runtime["action_gate"]["destructive_actions_ready"] is False
    assert "chassis_service_procedure_not_verified" in runtime["action_gate"]["blocked_by"]
    assert "backup_acknowledgement_required" in runtime["action_gate"]["blocked_by"]
    assert "replacement_candidate_not_validated" in runtime["action_gate"]["blocked_by"]


def test_resilver_moves_storage_guidance_to_monitor_recovery():
    payload = {
        "storage": {
            "pools": [{"name": "HDDs", "health": "DEGRADED"}],
            "zfs_activity": {
                "resilver_running": True,
                "percent": 31,
                "remaining": "2h14m to go",
            },
        }
    }

    guidance = guidance_for_snapshot(payload)
    pool = next(item for item in guidance if item["code"] == "storage.pool_degraded")

    assert pool["runtime"]["phase"] == "monitor_recovery"
    assert pool["runtime"]["evidence"]["resilver_state"]["percent"] == 31


def test_status_augmentation_publishes_guidance_without_mutating_source():
    source = {
        "schema_version": 1,
        "read_only": True,
        "storage": {
            "pools": [{"name": "HDDs", "health": "DEGRADED"}],
        },
    }

    augmented = augment_status_snapshot(source)

    assert "operator_guidance" not in source
    assert augmented["storage"] is source["storage"]
    assert [item["code"] for item in augmented["operator_guidance"]] == [
        "storage.pool_degraded"
    ]
