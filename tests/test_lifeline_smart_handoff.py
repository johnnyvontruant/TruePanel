import json

from truepanel.lifeline import LifelineSessionStore


def _device(*, serial_last4="OLD3", zfs_state="ONLINE"):
    return {
        "pool": "HDDs",
        "vdev": "raidz1-0",
        "vdev_topology": "RAIDZ1",
        "remaining_redundancy": 0,
        "member_id": "member-3",
        "device": "sdc",
        "bay": 3,
        "model": "ST8000NE001",
        "serial_last4": serial_last4,
        "capacity_bytes": 8_000_000_000_000,
        "zfs_state": zfs_state,
    }


def critical_smart_payload():
    return {
        "storage": {
            "pools": [{"name": "HDDs", "health": "ONLINE"}],
            "zfs_activity": {"resilver_running": False},
            "devices": [_device()],
        },
        "operator_guidance": [
            {
                "code": "storage.smart_warning",
                "severity": "critical",
                "runtime": {
                    "disposition": "prepare_replacement",
                    "evidence": {
                        "pool": "HDDs",
                        "vdev": "raidz1-0",
                        "device": "sdc",
                        "bay": 3,
                        "model": "ST8000NE001",
                        "serial_last4": "OLD3",
                        "smart_health": "PASSED",
                        "reallocated": 15_952,
                        "pending": 1_608,
                        "offline_uncorrectable": 1_608,
                        "reported_uncorrect": 905,
                        "media_errors": 0,
                        "critical_warning": None,
                        "zfs_state": "ONLINE",
                    },
                },
            }
        ],
    }


def caution_smart_payload():
    payload = critical_smart_payload()
    card = payload["operator_guidance"][0]
    card["severity"] = "caution"
    card["runtime"].pop("disposition", None)
    evidence = card["runtime"]["evidence"]
    evidence["reallocated"] = 15
    evidence["pending"] = 0
    evidence["offline_uncorrectable"] = 0
    evidence["reported_uncorrect"] = 4
    return payload


def _clean_smart_record(*, serial_last4):
    return {
        "pool": "HDDs",
        "vdev": "raidz1-0",
        "device": "sdc",
        "bay": 3,
        "serial_last4": serial_last4,
        "health": "PASSED",
        "reallocated": 0,
        "pending": 0,
        "offline_uncorrectable": 0,
        "reported_uncorrect": 0,
        "media_errors": 0,
        "critical_warning": None,
        "zfs_state": "ONLINE",
    }


def clean_same_drive_payload():
    return {
        "storage": {
            "pools": [{"name": "HDDs", "health": "ONLINE"}],
            "zfs_activity": {"resilver_running": False},
            "devices": [_device()],
            "smart": [_clean_smart_record(serial_last4="OLD3")],
        },
        "operator_guidance": [],
    }


def clean_replacement_payload():
    return {
        "storage": {
            "pools": [{"name": "HDDs", "health": "ONLINE"}],
            "zfs_activity": {"resilver_running": False},
            "devices": [_device(serial_last4="NEW3")],
            "smart": [_clean_smart_record(serial_last4="NEW3")],
        },
        "operator_guidance": [],
    }


def disk_fault_payload():
    device = _device(zfs_state="FAULTED")
    return {
        "storage": {
            "pools": [{"name": "HDDs", "health": "DEGRADED"}],
            "zfs_activity": {"resilver_running": False},
            "devices": [device],
        },
        "operator_guidance": [
            {
                "code": "storage.disk_faulted",
                "runtime": {"evidence": dict(device)},
            }
        ],
    }


def test_critical_smart_opens_prefailure_session_while_zfs_online(tmp_path):
    path = tmp_path / "lifeline.json"
    store = LifelineSessionStore(path=path, clock=lambda: 100.0)

    payload = store.observe(critical_smart_payload())
    session = payload["lifeline"]["sessions"][0]

    assert session["status"] == "active"
    assert session["trigger_code"] == "storage.smart_warning"
    assert session["trigger_kind"] == "critical_smart_prefailure"
    assert session["original_fault"]["zfs_state"] == "ONLINE"
    assert session["last_session"]["code"] == "storage.smart_warning"
    assert session["last_session"]["phase"] == "prepare"
    assert session["last_session"]["can_identify_bay"] is True
    assert session["healthy_observations"] == 0

    persisted = json.loads(path.read_text(encoding="utf-8"))
    original = next(iter(persisted["sessions"].values()))["original_fault"]
    assert "pending" not in original
    assert "offline_uncorrectable" not in original
    assert "reported_uncorrect" not in original


def test_caution_only_smart_does_not_open_lifeline(tmp_path):
    store = LifelineSessionStore(path=tmp_path / "lifeline.json")

    payload = store.observe(caution_smart_payload())

    assert payload["lifeline"]["sessions"] == []


def test_prefailure_session_never_self_clears_while_smart_is_critical(tmp_path):
    store = LifelineSessionStore(path=tmp_path / "lifeline.json")
    store.observe(critical_smart_payload())

    payload = None
    for _ in range(5):
        payload = store.observe(critical_smart_payload())

    session = payload["lifeline"]["sessions"][0]
    assert session["status"] == "active"
    assert session["healthy_observations"] == 0


def test_prefailure_session_never_self_clears_without_replacement_identity(tmp_path):
    store = LifelineSessionStore(path=tmp_path / "lifeline.json")
    store.observe(critical_smart_payload())

    payload = None
    for _ in range(5):
        payload = store.observe(clean_same_drive_payload())

    session = payload["lifeline"]["sessions"][0]
    assert session["status"] == "active"
    assert session["healthy_observations"] == 0


def test_prefailure_completion_requires_replacement_and_three_clean_observations(
    tmp_path,
):
    store = LifelineSessionStore(path=tmp_path / "lifeline.json")
    observed = store.observe(critical_smart_payload())
    session_id = observed["lifeline"]["sessions"][0]["id"]

    store.set_service_procedure_verified(
        session_id,
        verified=True,
        profile="qnap-tvs-x71",
        source="verified-profile",
    )
    store.acknowledge(session_id, "backup_state", True)
    store.set_replacement_candidates(
        session_id,
        [
            {
                "device": "sdh",
                "capacity_bytes": 8_000_000_000_000,
                "member_of_pool": False,
                "contains_preserved_data": False,
            }
        ],
    )
    store.observe(critical_smart_payload())

    first = store.observe(clean_replacement_payload())
    second = store.observe(clean_replacement_payload())
    third = store.observe(clean_replacement_payload())

    assert first["lifeline"]["sessions"][0]["healthy_observations"] == 1
    assert second["lifeline"]["sessions"][0]["healthy_observations"] == 2
    session = third["lifeline"]["sessions"][0]
    assert session["healthy_observations"] == 3
    assert session["status"] == "completed"
    assert session["last_session"]["phase"] == "complete"
    assert session["last_session"]["recovery_verified"] is True


def test_existing_disk_fault_completion_contract_is_unchanged(tmp_path):
    store = LifelineSessionStore(path=tmp_path / "lifeline.json")
    store.observe(disk_fault_payload())

    clean = clean_same_drive_payload()
    first = store.observe(clean)
    second = store.observe(clean)
    third = store.observe(clean)

    assert first["lifeline"]["sessions"][0]["healthy_observations"] == 1
    assert second["lifeline"]["sessions"][0]["healthy_observations"] == 2
    session = third["lifeline"]["sessions"][0]
    assert session["healthy_observations"] == 3
    assert session["status"] == "completed"
