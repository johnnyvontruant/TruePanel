import json
from types import SimpleNamespace

from truepanel.lifeline.identity import DriveIdentityResolver
from truepanel.lifeline.replacement import (
    ReplacementCandidateProvider,
    parse_block_signatures,
)


def device(
    name,
    *,
    bay=3,
    serial="NEW00002",
    size=8_000_000_000_000,
    category="front-bay",
):
    return SimpleNamespace(
        device=name,
        physical_bay=bay,
        serial=serial,
        model="ST8000NE001",
        category=category,
        mapping_source="enclosure",
        drive=SimpleNamespace(size_bytes=size),
    )


class Inventory:
    def __init__(self, *items):
        self._items = list(items)

    def devices(self):
        return list(self._items)

    def find_device(self, name):
        for item in self._items:
            if item.device == name:
                return item
        return None


def signatures(*nodes):
    return json.dumps({"blockdevices": list(nodes)})


def clean_disk(name="sdc"):
    return {
        "name": name,
        "type": "disk",
        "size": 8_000_000_000_000,
        "fstype": None,
        "pttype": None,
        "mountpoints": [None],
    }


def used_disk(name="sdc"):
    return {
        "name": name,
        "type": "disk",
        "size": 8_000_000_000_000,
        "fstype": None,
        "pttype": "gpt",
        "mountpoints": [None],
        "children": [
            {
                "name": f"{name}1",
                "type": "part",
                "fstype": "zfs_member",
                "pttype": None,
                "mountpoints": [None],
            }
        ],
    }


def fault(**overrides):
    payload = {
        "device": "sdc",
        "bay": 3,
        "serial_last4": "0001",
        "capacity_bytes": 8_000_000_000_000,
    }
    payload.update(overrides)
    return payload


def test_signature_parser_marks_partitions_and_filesystems_as_data():
    parsed = parse_block_signatures(
        signatures(clean_disk("sda"), used_disk("sdb"))
    )

    assert parsed == {"sda": False, "sdb": True}


def test_same_slot_new_serial_can_be_replacement_candidate():
    provider = ReplacementCandidateProvider(
        inventory=Inventory(device("sdc", serial="NEW00002")),
        signature_runner=lambda: signatures(clean_disk()),
    )

    candidates = provider.candidates(
        fault(),
        storage_devices=[
            {
                "device": "sdc",
                "zfs_state": "FAULTED",
            }
        ],
    )

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate["device"] == "sdc"
    assert candidate["same_slot_replacement"] is True
    assert candidate["member_of_pool"] is False
    assert candidate["contains_preserved_data"] is False
    assert candidate["ambiguous"] is False


def test_same_path_without_serial_change_is_not_a_replacement():
    provider = ReplacementCandidateProvider(
        inventory=Inventory(device("sdc", serial="OLD00001")),
        signature_runner=lambda: signatures(clean_disk()),
    )

    assert provider.candidates(fault()) == []


def test_existing_partition_signature_is_preserve_data_risk():
    provider = ReplacementCandidateProvider(
        inventory=Inventory(device("sdc")),
        signature_runner=lambda: signatures(used_disk()),
    )

    candidate = provider.candidates(fault())[0]

    assert candidate["contains_preserved_data"] is True


def test_unknown_signature_state_fails_closed_as_preserve_data_risk():
    provider = ReplacementCandidateProvider(
        inventory=Inventory(device("sdc")),
        signature_runner=lambda: "not-json",
    )

    candidate = provider.candidates(fault())[0]

    assert candidate["contains_preserved_data"] is True


def test_undersized_media_is_discovered_but_validator_can_reject_it():
    provider = ReplacementCandidateProvider(
        inventory=Inventory(device("sdc", size=7_000_000_000_000)),
        signature_runner=lambda: signatures(clean_disk()),
    )

    candidate = provider.candidates(fault())[0]

    assert candidate["capacity_bytes"] == 7_000_000_000_000
    assert candidate["minimum_capacity_bytes"] == 8_000_000_000_000


def test_boot_and_internal_nvme_are_never_drive_replacement_candidates():
    provider = ReplacementCandidateProvider(
        inventory=Inventory(
            device("sda", category="boot-media", bay=None),
            device("nvme0n1", category="internal-nvme", bay=None),
        ),
        signature_runner=lambda: signatures(),
    )

    assert provider.candidates(fault()) == []


def test_known_failed_bay_hides_other_bays_from_same_slot_workflow():
    provider = ReplacementCandidateProvider(
        inventory=Inventory(
            device("sdc", bay=3),
            device("sdd", bay=4, serial="OTHER004"),
        ),
        signature_runner=lambda: signatures(clean_disk("sdc"), clean_disk("sdd")),
    )

    candidates = provider.candidates(fault())

    assert [item["bay"] for item in candidates] == [3]


def test_online_zfs_member_is_not_recommended_as_free_media():
    provider = ReplacementCandidateProvider(
        inventory=Inventory(device("sdc", serial="NEW00002")),
        signature_runner=lambda: signatures(clean_disk()),
    )

    candidate = provider.candidates(
        fault(),
        storage_devices=[{"device": "sdc", "zfs_state": "ONLINE"}],
    )[0]

    assert candidate["member_of_pool"] is True



def _stable_identity(name, serial):
    inventory = Inventory(device(name, serial=serial))
    resolver = DriveIdentityResolver(
        inventory=inventory,
        udev_runner=lambda unused_device: "",
    )
    identity = resolver.resolve(
        {
            "device": name,
            "bay": 3,
            "model": "ST8000NE001",
            "serial_last4": serial[-4:],
            "capacity_bytes": 8_000_000_000_000,
        }
    )
    assert identity is not None
    return identity.to_public_dict()


def test_original_disk_renamed_is_excluded_by_stable_identity():
    original_identity = _stable_identity("sdc", "OLD00001")
    inventory = Inventory(device("sda", serial="OLD00001"))
    resolver = DriveIdentityResolver(
        inventory=inventory,
        udev_runner=lambda unused_device: "",
    )
    provider = ReplacementCandidateProvider(
        inventory=inventory,
        identity_resolver=resolver,
        signature_runner=lambda: signatures(clean_disk("sda")),
    )

    candidates = provider.candidates(
        fault(
            device="sdc",
            serial_last4=None,
            drive_identity=original_identity,
        ),
        storage_devices=[
            {
                "device": "sda",
                "zfs_state": "FAULTED",
            }
        ],
    )

    assert candidates == []


def test_new_disk_can_reuse_failed_runtime_path_when_identity_differs():
    original_identity = _stable_identity("sdc", "OLD00001")
    inventory = Inventory(device("sdc", serial="NEW00002"))
    resolver = DriveIdentityResolver(
        inventory=inventory,
        udev_runner=lambda unused_device: "",
    )
    provider = ReplacementCandidateProvider(
        inventory=inventory,
        identity_resolver=resolver,
        signature_runner=lambda: signatures(clean_disk("sdc")),
    )

    candidates = provider.candidates(
        fault(
            serial_last4=None,
            drive_identity=original_identity,
        ),
        storage_devices=[
            {
                "device": "sdc",
                "zfs_state": "FAULTED",
            }
        ],
    )

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate["device"] == "sdc"
    assert candidate["identity_verified_distinct"] is True
    assert candidate["same_slot_replacement"] is True
    assert candidate["member_of_pool"] is False
    assert candidate["ambiguous"] is False


def test_unknown_identity_does_not_fabricate_replacement_candidate():
    inventory = Inventory(device("sdc", serial=""))
    resolver = DriveIdentityResolver(
        inventory=inventory,
        udev_runner=lambda unused_device: "",
    )
    provider = ReplacementCandidateProvider(
        inventory=inventory,
        identity_resolver=resolver,
        signature_runner=lambda: signatures(clean_disk("sdc")),
    )

    assert provider.candidates(
        fault(
            serial_last4=None,
            drive_identity=None,
        )
    ) == []
