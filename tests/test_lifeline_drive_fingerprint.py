import os
from copy import deepcopy
from types import SimpleNamespace

from truepanel.lifeline.fingerprint import (
    DriveFingerprintProvider,
    DriveFingerprintStore,
)
from truepanel.web.snapshot import SnapshotService


MEMBER = "15571478626791065431"
PARTUUID = "389d5fd4-8899-434f-b171-ef29d8937033"
CAPACITY = 8_001_563_222_016


PATH_STATUS = f"""
  pool: HDDs
 state: ONLINE
config:

        NAME           STATE     READ WRITE CKSUM
        HDDs           ONLINE       0     0     0
          raidz1-0     ONLINE       0     0     0
            /dev/sdg1  ONLINE       0     0     0

errors: No known data errors
"""


GUID_STATUS = f"""
  pool: HDDs
 state: ONLINE
config:

        NAME                      STATE     READ WRITE CKSUM
        11111111111111111111      ONLINE       0     0     0
          2222222222222222222     ONLINE       0     0     0
            {MEMBER}              ONLINE       0     0     0

errors: No known data errors
"""


class Inventory:
    def __init__(self, *, serial="WKD3MW6D", bay=3, mapping_source="kernel"):
        self._item = SimpleNamespace(
            device="sdg",
            category="front-bay",
            physical_bay=bay,
            mapping_source=mapping_source,
            enclosure="6:0:0:0",
            serial=serial,
            model="ST8000NE001-2M7101",
            drive=SimpleNamespace(size_bytes=CAPACITY),
        )

    def devices(self):
        return [self._item]


def udev(device):
    if device == "/dev/sdg1":
        return f"ID_PART_ENTRY_UUID={PARTUUID}\nID_PATH=pci-test-ata-3.0\n"
    if device == "/dev/sdg":
        return "ID_WWN=0x5000c500cd3caaae\nID_SERIAL_SHORT=WKD3MW6D\n"
    return ""


def fingerprint_provider(**kwargs):
    return DriveFingerprintProvider(
        inventory=kwargs.pop("inventory", Inventory()),
        path_status_runner=lambda: PATH_STATUS,
        guid_status_runner=lambda: GUID_STATUS,
        udev_runner=udev,
        refresh_seconds=0,
        **kwargs,
    )


def test_provider_cross_checks_healthy_member_guid_to_bay_and_media():
    records = fingerprint_provider(clock=lambda: 100.0).fingerprints()

    assert records == [
        {
            "verified": True,
            "pool": "HDDs",
            "vdev": "raidz1-0",
            "vdev_topology": "RAIDZ1",
            "member_guid": MEMBER,
            "partuuid": PARTUUID,
            "zfs_path": "/dev/sdg1",
            "device": "sdg",
            "physical_bay": 3,
            "mapping_source": "kernel",
            "enclosure": "6:0:0:0",
            "model": "ST8000NE001-2M7101",
            "serial": "WKD3MW6D",
            "serial_last4": "MW6D",
            "wwn": "0x5000c500cd3caaae",
            "capacity_bytes": CAPACITY,
            "observed_at": 100.0,
            "source": "healthy_pool_cross_check",
        }
    ]


def test_provider_refuses_untrusted_config_only_bay_mapping():
    records = fingerprint_provider(
        inventory=Inventory(mapping_source="configured"),
        clock=lambda: 100.0,
    ).fingerprints()

    assert len(records) == 1
    assert records[0]["verified"] is False


def test_provider_refuses_misaligned_guid_tree():
    broken = GUID_STATUS.replace("ONLINE       0     0     0", "ONLINE       1     0     0", 1)
    provider = DriveFingerprintProvider(
        inventory=Inventory(),
        path_status_runner=lambda: PATH_STATUS,
        guid_status_runner=lambda: broken,
        udev_runner=udev,
        refresh_seconds=0,
    )

    assert provider.fingerprints() == []


def test_fingerprint_store_survives_device_rename_and_locks_identity_conflict(tmp_path):
    now = [100.0]
    path = tmp_path / "fingerprints.json"
    store = DriveFingerprintStore(path=path, clock=lambda: now[0])
    record = fingerprint_provider(clock=lambda: 90.0).fingerprints()[0]

    assert store.record([record]) is True
    assert os.stat(path).st_mode & 0o777 == 0o600

    now[0] = 110.0
    renamed = deepcopy(record)
    renamed["device"] = "sdh"
    renamed["zfs_path"] = "/dev/sdh1"
    renamed["observed_at"] = 110.0
    assert store.record([renamed]) is True

    saved = store.lookup("HDDs", MEMBER)
    assert saved is not None
    assert saved["device"] == "sdh"
    assert saved["serial"] == "WKD3MW6D"
    assert saved["observations"] == 2

    now[0] = 120.0
    conflict = deepcopy(renamed)
    conflict["serial"] = "DIFFERENT"
    conflict["serial_last4"] = "RENT"
    conflict["observed_at"] = 120.0
    assert store.record([conflict]) is True

    assert store.lookup("HDDs", MEMBER) is None
    summary = store.snapshot()
    assert summary["count"] == 1
    assert summary["conflicted"] == 1


class HealthyCollector:
    def update(self):
        return {
            "pools": [{"name": "HDDs", "health": "ONLINE"}],
            "storage_devices": [],
            "zfs_activity": {"resilver_running": False},
        }


class MissingCollector:
    def update(self):
        return {
            "pools": [{"name": "HDDs", "health": "DEGRADED"}],
            "storage_devices": [
                {
                    "pool": "HDDs",
                    "pool_state": "DEGRADED",
                    "vdev": "raidz1-0",
                    "vdev_topology": "RAIDZ1",
                    "remaining_redundancy": 0,
                    "member_id": MEMBER,
                    "historical_path": f"/dev/disk/by-partuuid/{PARTUUID}",
                    "device": None,
                    "physical_bay": None,
                    "model": None,
                    "serial_last4": None,
                    "capacity_bytes": None,
                    "present": False,
                    "zfs_state": "UNAVAIL",
                    "read_errors": 0,
                    "write_errors": 0,
                    "checksum_errors": 0,
                }
            ],
            "zfs_activity": {"resilver_running": False},
        }


def config():
    return {
        "hardware": {
            "lifeline": {
                "service_profile": "qnap-tvs-x71",
                "chassis_model": "TVS-671",
            }
        },
        "history": {},
    }


class NoFingerprints:
    def fingerprints(self):
        return []


class NoCandidates:
    def candidates(self, *args, **kwargs):
        return []


def test_snapshot_uses_last_known_good_fingerprint_when_same_member_disappears(tmp_path):
    fingerprint_path = tmp_path / "drive-fingerprints.json"
    fingerprint_store = DriveFingerprintStore(
        path=fingerprint_path,
        clock=lambda: 100.0,
    )
    fingerprint = fingerprint_provider(clock=lambda: 90.0).fingerprints()[0]
    fingerprint_store.record([fingerprint])

    service = SnapshotService(
        collector=MissingCollector(),
        config=config(),
        lifeline_path=tmp_path / "lifeline.json",
        drive_fingerprint_provider=NoFingerprints(),
        drive_fingerprint_store=fingerprint_store,
        replacement_candidate_provider=NoCandidates(),
        fan_status_provider=lambda: {},
        clock=lambda: 100.0,
    )

    payload = service.status()
    session = payload["lifeline"]["sessions"][0]
    original = session["original_fault"]
    repair = session["last_session"]
    context = session["context"]

    assert original["member_id"] == MEMBER
    assert original["bay"] is None
    assert original["capacity_bytes"] is None
    assert original["serial_last4"] is None

    assert repair["target"]["bay"] == 3
    assert repair["target"]["capacity_bytes"] == CAPACITY
    assert repair["target"]["capacity_source"] == "historical_verified"
    assert repair["target"]["physical_identity_serial_last4"] == "MW6D"
    assert repair["can_identify_bay"] is True
    assert repair["can_execute_replacement"] is False

    assert context["physical_identity"]["member_id"] == MEMBER
    assert context["physical_identity"]["bay"] == 3
    assert context["historical_media"]["capacity_bytes"] == CAPACITY
    assert context["historical_media"]["model"] == "ST8000NE001-2M7101"
    assert context["historical_media"]["source"] == (
        "TruePanel last-known-good healthy drive fingerprint"
    )

    assert payload["lifeline"]["drive_fingerprints"] == {
        "schema_version": 1,
        "metadata_only": True,
        "count": 1,
        "conflicted": 0,
    }


def test_snapshot_rejects_fingerprint_when_partuuid_does_not_match_fault(tmp_path):
    store = DriveFingerprintStore(
        path=tmp_path / "drive-fingerprints.json",
        clock=lambda: 100.0,
    )
    fingerprint = fingerprint_provider(clock=lambda: 90.0).fingerprints()[0]
    fingerprint["partuuid"] = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    store.record([fingerprint])

    service = SnapshotService(
        collector=MissingCollector(),
        config=config(),
        lifeline_path=tmp_path / "lifeline.json",
        drive_fingerprint_provider=NoFingerprints(),
        drive_fingerprint_store=store,
        replacement_candidate_provider=NoCandidates(),
        fan_status_provider=lambda: {},
        clock=lambda: 100.0,
    )

    payload = service.status()
    session = payload["lifeline"]["sessions"][0]
    repair = session["last_session"]

    assert repair["phase"] == "identify"
    assert repair["target"]["bay"] is None
    assert repair["target"]["capacity_bytes"] is None
    assert repair["can_identify_bay"] is False
    assert repair["can_execute_replacement"] is False
