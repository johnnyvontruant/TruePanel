import json

from truepanel.lifeline import LifelineSessionStore
from truepanel.lifeline.identity import DriveIdentity


CAPACITY = 8_001_563_222_016
TOKEN_A = "a" * 24
TOKEN_B = "b" * 24
TOKEN_C = "c" * 24


def identity(token=TOKEN_A, *, mode="wwn", device="sda"):
    confidence = {
        "wwn": "very_high",
        "serial_model": "high",
        "zfs_member": "high",
        "correlated_evidence": "medium",
        "legacy_runtime_address": "low",
    }[mode]
    return DriveIdentity(
        stable_key=f"{mode if mode != 'serial_model' else 'serial'}:{token}",
        mode=mode,
        confidence=confidence,
        source="test",
        token=token,
        device=device,
        bay=3,
        model="ST8000NE001-2M7101",
        serial_last4="MW6D",
        capacity_bytes=CAPACITY,
    )


class FixedResolver:
    def __init__(self, value):
        self.value = value

    def resolve(self, _evidence):
        return self.value


class DeviceResolver:
    def __init__(self, values):
        self.values = values

    def resolve(self, evidence):
        return self.values[evidence["device"]]


class SequenceResolver:
    def __init__(self, values):
        self.values = list(values)

    def resolve(self, _evidence):
        return self.values.pop(0)


def smart_evidence(device):
    return {
        "pool": "HDDs",
        "vdev": "raidz1-0",
        "vdev_topology": "RAIDZ1",
        "remaining_redundancy": 1,
        "device": device,
        "member_id": f"/dev/{device}1",
        "bay": 3,
        "model": "ST8000NE001-2M71",
        "serial_last4": "MW6D",
        "capacity_bytes": CAPACITY,
        "zfs_state": "ONLINE",
        "smart_health": "PASSED",
        "critical_warning": "0x00",
        "pending": 1608,
        "offline_uncorrectable": 1608,
        "reallocated": 15952,
        "reported_uncorrect": 905,
        "media_errors": 0,
    }


def payload(device):
    evidence = smart_evidence(device)
    return {
        "storage": {
            "pools": [{"name": "HDDs", "health": "ONLINE"}],
            "devices": [dict(evidence)],
            "zfs_activity": {"resilver_running": False},
        },
        "operator_guidance": [
            {
                "code": "storage.smart_warning",
                "severity": "critical",
                "runtime": {
                    "active": True,
                    "disposition": "prepare_replacement",
                    "evidence": dict(evidence),
                },
            }
        ],
    }


def seed_legacy_aliases(path):
    current_time = [100.0]

    def clock():
        return current_time[0]

    store = LifelineSessionStore(
        path=path,
        clock=clock,
        identity_resolver=FixedResolver(None),
    )
    with store._lock:
        for device in ("sdc", "sdd", "sda"):
            evidence = smart_evidence(device)
            key = f"drive:HDDs:raidz1-0:{device}"
            ledger = store._new_smart_session(key, evidence, identity=None)
            ledger["updated_at"] = current_time[0]
            current_time[0] += 10.0
        store._save()


def test_live_sdc_sdd_sda_aliases_collapse_to_one_stable_incident(tmp_path):
    path = tmp_path / "sessions.json"
    seed_legacy_aliases(path)

    store = LifelineSessionStore(
        path=path,
        clock=lambda: 200.0,
        identity_resolver=FixedResolver(identity(device="sda")),
    )
    observed = store.observe(payload("sda"))
    sessions = observed["lifeline"]["sessions"]

    active = [item for item in sessions if item["status"] == "active"]
    superseded = [
        item for item in sessions if item["status"] == "superseded"
    ]

    assert len(active) == 1
    assert len(superseded) == 2

    canonical = active[0]
    assert canonical["fault_key"] == f"drive:HDDs:raidz1-0:wwn:{TOKEN_A}"
    assert canonical["id"] == (
        f"drive:HDDs:raidz1-0:wwn:{TOKEN_A}:attempt-1"
    )
    assert canonical["current_device"] == "sda"
    assert canonical["original_fault"]["device"] == "sda"
    assert canonical["original_fault"]["member_id"] == "/dev/sda1"
    assert canonical["device_history"] == ["sdc", "sdd", "sda"]
    assert len(canonical["legacy_ids"]) == 3
    assert len(canonical["legacy_fault_keys"]) == 3
    assert canonical["drive_identity"]["mode"] == "wwn"
    assert canonical["drive_identity"]["raw_serial_exposed"] is False
    assert canonical["drive_identity"]["raw_wwn_exposed"] is False

    for alias in superseded:
        assert alias["superseded_by"] == canonical["id"]
        assert alias["superseded_at"] == 200.0

    rendered = json.dumps(observed, sort_keys=True)
    assert "WKD3MW6D" not in rendered
    assert "5000c500" not in rendered

    checklist_repair = observed["operator_guidance"][0]["repair_session"]
    assert checklist_repair["can_execute_replacement"] is False


def test_device_rename_reuses_stable_session_and_appends_history(tmp_path):
    path = tmp_path / "sessions.json"
    stable = identity(device="sdc")
    resolver = FixedResolver(stable)
    store = LifelineSessionStore(path=path, identity_resolver=resolver)

    first = store.observe(payload("sdc"))
    first_active = [
        item for item in first["lifeline"]["sessions"]
        if item["status"] == "active"
    ][0]
    first_id = first_active["id"]

    resolver.value = identity(device="sda")
    renamed = store.observe(payload("sda"))
    active = [
        item for item in renamed["lifeline"]["sessions"]
        if item["status"] == "active"
    ]

    assert len(active) == 1
    assert active[0]["id"] == first_id
    assert active[0]["fault_key"] == f"drive:HDDs:raidz1-0:wwn:{TOKEN_A}"
    assert active[0]["current_device"] == "sda"
    assert active[0]["device_history"] == ["sdc", "sda"]


def test_different_strong_wwn_does_not_merge_even_in_same_bay(tmp_path):
    resolver = DeviceResolver(
        {
            "sda": identity(TOKEN_A, device="sda"),
            "sdb": identity(TOKEN_B, device="sdb"),
        }
    )
    store = LifelineSessionStore(
        path=tmp_path / "sessions.json",
        identity_resolver=resolver,
    )

    store.observe(payload("sda"))
    observed = store.observe(payload("sdb"))
    active = [
        item for item in observed["lifeline"]["sessions"]
        if item["status"] == "active"
    ]

    assert len(active) == 2
    assert {item["fault_key"] for item in active} == {
        f"drive:HDDs:raidz1-0:wwn:{TOKEN_A}",
        f"drive:HDDs:raidz1-0:wwn:{TOKEN_B}",
    }


def test_weaker_identity_observation_does_not_downgrade_existing_wwn(tmp_path):
    correlated = identity(
        TOKEN_C,
        mode="correlated_evidence",
        device="sda",
    )
    resolver = SequenceResolver(
        [
            identity(TOKEN_A, device="sda"),
            correlated,
        ]
    )
    store = LifelineSessionStore(
        path=tmp_path / "sessions.json",
        identity_resolver=resolver,
    )

    first = store.observe(payload("sda"))
    first_active = [
        item for item in first["lifeline"]["sessions"]
        if item["status"] == "active"
    ][0]

    second = store.observe(payload("sda"))
    second_active = [
        item for item in second["lifeline"]["sessions"]
        if item["status"] == "active"
    ][0]

    assert second_active["id"] == first_active["id"]
    assert second_active["fault_key"] == f"drive:HDDs:raidz1-0:wwn:{TOKEN_A}"
    assert second_active["drive_identity"]["mode"] == "wwn"
    assert second_active["drive_identity"]["stable_key"] == f"wwn:{TOKEN_A}"
