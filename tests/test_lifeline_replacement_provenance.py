import pytest

from truepanel.lifeline.session import evaluate_drive_repair
from truepanel.lifeline.store import LifelineSessionStore
from truepanel.web.snapshot import _replacement_fault_for_session


MEMBER = "15571478626791065431"


def fault_payload():
    return {
        "storage": {
            "pools": [{"name": "HDDs", "health": "DEGRADED"}],
            "zfs_activity": {"resilver_running": False},
        },
        "operator_guidance": [
            {
                "code": "storage.disk_faulted",
                "runtime": {
                    "evidence": {
                        "pool": "HDDs",
                        "pool_state": "DEGRADED",
                        "vdev": "raidz1-0",
                        "vdev_topology": "RAIDZ1",
                        "remaining_redundancy": 0,
                        "member_id": MEMBER,
                        "historical_path": (
                            "/dev/disk/by-partuuid/"
                            "389d5fd4-8899-434f-b171-ef29d8937033"
                        ),
                        "device": None,
                        "physical_bay": None,
                        "capacity_bytes": None,
                        "zfs_state": "UNAVAIL",
                        "resilver_state": {"resilver_running": False},
                    }
                },
            }
        ],
    }


def test_unknown_failed_capacity_fails_closed_for_otherwise_valid_media():
    repair = evaluate_drive_repair(
        {
            "pool": "HDDs",
            "pool_state": "DEGRADED",
            "vdev": "raidz1-0",
            "vdev_topology": "RAIDZ1",
            "remaining_redundancy": 0,
            "member_id": MEMBER,
            "device": "sdc",
            "bay": 3,
            "capacity_bytes": None,
            "zfs_state": "FAULTED",
            "resilver_state": {"resilver_running": False},
        },
        service_procedure_verified=True,
        backup_acknowledged=True,
        replacement_candidate={
            "device": "sdg",
            "model": "ST8000NE001",
            "capacity_bytes": 8_001_563_222_016,
            "member_of_pool": False,
            "contains_preserved_data": False,
            "ambiguous": False,
        },
    )

    assert repair.phase == "validate_replacement"
    assert repair.replacement.valid is False
    assert "replacement_minimum_capacity_not_verified" in repair.replacement.reasons
    assert repair.write_preconditions_complete is False
    assert repair.can_execute_replacement is False


def test_historical_media_requires_matching_commissioned_serial(tmp_path):
    store = LifelineSessionStore(path=tmp_path / "lifeline.json")
    observed = store.observe(fault_payload())
    session_id = observed["lifeline"]["sessions"][0]["id"]

    store.set_historical_physical_identity(
        session_id,
        member_id=MEMBER,
        bay=3,
        serial_last4="MW6D",
        source="archived identity diagnostic",
    )

    with pytest.raises(ValueError, match="verified matching physical identity"):
        store.set_historical_media_properties(
            session_id,
            member_id=MEMBER,
            serial_last4="WRONG",
            capacity_bytes=8_001_563_222_016,
            model="ST8000NE001-2M71",
            source="archived media inventory",
        )

    store.set_historical_media_properties(
        session_id,
        member_id=MEMBER,
        serial_last4="MW6D",
        capacity_bytes=8_001_563_222_016,
        model="ST8000NE001-2M71",
        source="archived media inventory",
    )

    observed = store.observe(fault_payload())
    session = observed["lifeline"]["sessions"][0]

    assert session["original_fault"]["capacity_bytes"] is None
    assert session["context"]["historical_media"] == {
        "verified": True,
        "kind": "historical_verified",
        "member_id": MEMBER,
        "serial_last4": "MW6D",
        "capacity_bytes": 8_001_563_222_016,
        "model": "ST8000NE001-2M71",
        "source": "archived media inventory",
    }
    assert session["last_session"]["target"]["capacity_bytes"] == 8_001_563_222_016
    assert session["last_session"]["target"]["capacity_source"] == "historical_verified"


def test_replacement_discovery_uses_verified_historical_target_without_mutation():
    session = {
        "original_fault": {
            "member_id": MEMBER,
            "device": None,
            "bay": None,
            "serial_last4": None,
            "capacity_bytes": None,
        },
        "last_session": {
            "target": {
                "member_id": MEMBER,
                "device": None,
                "bay": 3,
                "physical_identity_source": "historical_verified",
                "physical_identity_serial_last4": "MW6D",
                "capacity_bytes": 8_001_563_222_016,
                "capacity_source": "historical_verified",
            }
        },
    }

    original_before = dict(session["original_fault"])
    effective = _replacement_fault_for_session(session)

    assert effective["bay"] == 3
    assert effective["serial_last4"] == "MW6D"
    assert effective["capacity_bytes"] == 8_001_563_222_016
    assert effective["capacity_source"] == "historical_verified"
    assert session["original_fault"] == original_before


def test_unverified_target_cannot_scope_replacement_discovery():
    session = {
        "original_fault": {
            "member_id": MEMBER,
            "device": None,
            "bay": None,
        },
        "last_session": {
            "target": {
                "member_id": MEMBER,
                "bay": 3,
                "physical_identity_source": None,
            }
        },
    }

    effective = _replacement_fault_for_session(session)

    assert effective.get("bay") is None
