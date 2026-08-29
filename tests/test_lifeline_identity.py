from types import SimpleNamespace

from truepanel.lifeline.identity import DriveIdentityResolver


CAPACITY = 8_001_563_222_016


class FakeInventory:
    def __init__(self, entries):
        self.entries = dict(entries)

    def find_device(self, device):
        return self.entries.get(device)


def drive_entry(device, *, serial="WKD3MW6D", bay=3):
    return SimpleNamespace(
        device=device,
        serial=serial,
        model="ST8000NE001-2M7101",
        physical_bay=bay,
        drive=SimpleNamespace(size_bytes=CAPACITY),
    )


def evidence(device):
    return {
        "pool": "HDDs",
        "vdev": "raidz1-0",
        "device": device,
        "bay": 3,
        "model": "ST8000NE001-2M71",
        "serial_last4": "MW6D",
        "capacity_bytes": CAPACITY,
    }


def test_wwn_identity_survives_linux_device_rename():
    inventory = FakeInventory(
        {
            "sda": drive_entry("sda"),
            "sdc": drive_entry("sdc"),
        }
    )
    resolver = DriveIdentityResolver(
        inventory=inventory,
        udev_runner=lambda _device: "ID_WWN=0x5000c500deadbeef\n",
    )

    first = resolver.resolve(evidence("sda"))
    renamed = resolver.resolve(evidence("sdc"))

    assert first is not None
    assert renamed is not None
    assert first.mode == "wwn"
    assert first.confidence == "very_high"
    assert first.stable_key == renamed.stable_key
    assert "sda" not in first.stable_key
    assert "sdc" not in first.stable_key
    assert "5000c500deadbeef" not in first.stable_key


def test_serial_model_identity_is_stable_when_wwn_is_unavailable():
    inventory = FakeInventory(
        {
            "sda": drive_entry("sda"),
            "sdd": drive_entry("sdd"),
        }
    )
    resolver = DriveIdentityResolver(
        inventory=inventory,
        udev_runner=lambda _device: "",
    )

    first = resolver.resolve(evidence("sda"))
    renamed = resolver.resolve(evidence("sdd"))

    assert first is not None
    assert renamed is not None
    assert first.mode == "serial_model"
    assert first.stable_key == renamed.stable_key
    assert "WKD3MW6D" not in first.stable_key


def test_public_identity_never_exposes_raw_serial_or_wwn():
    resolver = DriveIdentityResolver(
        inventory=FakeInventory({"sda": drive_entry("sda")}),
        udev_runner=lambda _device: "ID_WWN=0x5000c500deadbeef\n",
    )

    identity = resolver.resolve(evidence("sda"))
    assert identity is not None
    public = identity.to_public_dict()
    rendered = repr(public)

    assert public["raw_serial_exposed"] is False
    assert public["raw_wwn_exposed"] is False
    assert "WKD3MW6D" not in rendered
    assert "5000c500deadbeef" not in rendered
    assert public["serial_last4"] == "MW6D"


def test_mismatched_inventory_identity_fails_closed_to_correlated_evidence():
    resolver = DriveIdentityResolver(
        inventory=FakeInventory(
            {"sda": drive_entry("sda", serial="DIFFERENT9999")}
        ),
        udev_runner=lambda _device: "ID_WWN=0xWRONG\n",
    )

    identity = resolver.resolve(evidence("sda"))

    assert identity is not None
    assert identity.mode == "correlated_evidence"
    assert identity.confidence == "medium"
    assert identity.source == "bay_model_serial_suffix"


def test_correlated_fallback_ignores_rotating_device_name():
    resolver = DriveIdentityResolver(
        inventory=FakeInventory({}),
        udev_runner=lambda _device: "",
    )

    first = resolver.resolve(evidence("sdc"))
    renamed = resolver.resolve(evidence("sda"))

    assert first is not None
    assert renamed is not None
    assert first.mode == "correlated_evidence"
    assert first.stable_key == renamed.stable_key
