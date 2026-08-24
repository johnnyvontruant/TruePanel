from types import SimpleNamespace

from truepanel.guidance.storage_evidence import (
    StorageRecoveryEvidenceProvider,
    normalize_device,
    parse_zpool_status,
)


RAIDZ1_STATUS = """
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


LIVE_MISSING_STATUS = """
  pool: HDDs
 state: DEGRADED
config:

        NAME                      STATE     READ WRITE CKSUM
        HDDs                      DEGRADED     0     0     0
          raidz1-0                DEGRADED     0     0     0
            /dev/sda1             ONLINE       0     0     0
            /dev/sdb1             ONLINE       0     0     0
            15571478626791065431  UNAVAIL      0     0     0  was /dev/disk/by-partuuid/389d5fd4-8899-434f-b171-ef29d8937033
            /dev/sde1             ONLINE       0     0     0

errors: No known data errors
"""


def inventory_item(device, bay, *, serial="SERIAL1234", size=8_000_000_000_000):
    return SimpleNamespace(
        device=device,
        physical_bay=bay,
        model="ST8000NE001",
        serial=serial,
        mapping_source="enclosure",
        enclosure="6:0:0:0",
        label=f"Front Bay {bay}",
        drive=SimpleNamespace(size_bytes=size),
    )


class FakeInventory:
    def __init__(self, items):
        self._items = list(items)

    def devices(self):
        return list(self._items)


def test_normalize_device_collapses_partition_paths_to_whole_disks():
    assert normalize_device("/dev/sdc2") == "sdc"
    assert normalize_device("/dev/nvme0n1p3") == "nvme0n1"
    assert normalize_device("/dev/mmcblk0p2") == "mmcblk0"
    assert normalize_device("17384920394820394820") is None


def test_normalize_device_does_not_turn_dev_disk_alias_into_linux_device():
    value = (
        "15571478626791065431 UNAVAIL 0 0 0 "
        "was /dev/disk/by-partuuid/389d5fd4-8899-434f-b171-ef29d8937033"
    )
    assert normalize_device(value) is None


def test_parse_raidz1_fault_preserves_member_errors_and_redundancy():
    records = parse_zpool_status(RAIDZ1_STATUS)
    faulted = next(item for item in records if item["zfs_state"] == "FAULTED")

    assert faulted["pool"] == "HDDs"
    assert faulted["vdev"] == "raidz1-0"
    assert faulted["vdev_topology"] == "RAIDZ1"
    assert faulted["remaining_redundancy"] == 0
    assert faulted["device"] == "sdc"
    assert faulted["member_id"] == "/dev/sdc2"
    assert faulted["historical_path"] is None
    assert faulted["read_errors"] == 8
    assert faulted["write_errors"] == 0
    assert faulted["checksum_errors"] == 2


def test_live_missing_member_keeps_logical_identity_without_fake_device():
    records = parse_zpool_status(LIVE_MISSING_STATUS)
    missing = next(item for item in records if item["zfs_state"] == "UNAVAIL")

    assert missing["member_id"] == "15571478626791065431"
    assert missing["device"] is None
    assert missing["historical_path"] == (
        "/dev/disk/by-partuuid/389d5fd4-8899-434f-b171-ef29d8937033"
    )
    assert missing["remaining_redundancy"] == 0


def test_provider_only_publishes_bay_when_inventory_confirms_exact_device():
    inventory = FakeInventory(
        [
            inventory_item("sda", 1),
            inventory_item("sdb", 2),
            inventory_item("sdc", 3, serial="WKD3MW4K"),
            inventory_item("sdd", 4),
        ]
    )
    provider = StorageRecoveryEvidenceProvider(
        inventory=inventory,
        runner=lambda: RAIDZ1_STATUS,
    )

    faulted = next(
        item
        for item in provider.records()
        if item["zfs_state"] == "FAULTED"
    )

    assert faulted["device"] == "sdc"
    assert faulted["physical_bay"] == 3
    assert faulted["model"] == "ST8000NE001"
    assert faulted["serial_last4"] == "MW4K"
    assert faulted["capacity_bytes"] == 8_000_000_000_000
    assert faulted["present"] is True
    assert faulted["mapping_source"] == "enclosure"


def test_unattached_or_unresolved_member_never_gets_guessed_bay():
    status = RAIDZ1_STATUS.replace(
        "/dev/sdc2 FAULTED",
        "17384920394820394820 FAULTED",
    )
    provider = StorageRecoveryEvidenceProvider(
        inventory=FakeInventory(
            [inventory_item("sda", 1), inventory_item("sdb", 2)]
        ),
        runner=lambda: status,
    )

    faulted = next(
        item
        for item in provider.records()
        if item["zfs_state"] == "FAULTED"
    )

    assert faulted["member_id"] == "17384920394820394820"
    assert faulted["device"] is None
    assert faulted["physical_bay"] is None
    assert faulted["present"] is False


def test_by_partuuid_missing_member_never_gets_guessed_bay():
    provider = StorageRecoveryEvidenceProvider(
        inventory=FakeInventory(
            [inventory_item("sda", 1), inventory_item("sdb", 2)]
        ),
        runner=lambda: LIVE_MISSING_STATUS,
    )

    missing = next(
        item
        for item in provider.records()
        if item["zfs_state"] == "UNAVAIL"
    )

    assert missing["member_id"] == "15571478626791065431"
    assert missing["device"] is None
    assert missing["physical_bay"] is None
    assert missing["present"] is False


def test_mirror_remaining_redundancy_is_computed_from_member_count():
    status = """
  pool: SSDs
 state: DEGRADED
config:

        NAME          STATE     READ WRITE CKSUM
        SSDs          DEGRADED     0     0     0
          mirror-0    DEGRADED     0     0     0
            /dev/nvme0n1p3 ONLINE  0     0     0
            /dev/nvme1n1p3 FAULTED 0     0     1

errors: No known data errors
"""
    records = parse_zpool_status(status)

    assert len(records) == 2
    assert {item["vdev_topology"] for item in records} == {"MIRROR"}
    assert {item["remaining_redundancy"] for item in records} == {0}
