import argparse
import json
from dataclasses import dataclass
from pathlib import Path

from truepanel.hardware.commands import (
    add_hardware_subcommands,
    build_storage_report,
    build_summary_report,
    build_topology_report,
    handle_hardware_command,
)
from truepanel.hardware.inventory import Drive, StorageDevice


@dataclass(frozen=True)
class FakeBay:
    physical_bay: int
    kernel_slot: int
    installed: bool
    status: str
    device: str
    model: str
    serial: str
    wwid: str
    enclosure: str
    mapping_source: str

    @property
    def device_path(self):
        return f"/dev/{self.device}" if self.device else ""


def make_drive(
    device,
    serial,
    *,
    model="ST8000NE001",
    transport="sata",
    removable=False,
    size_bytes=8_000_000_000_000,
):
    return Drive(
        device=device,
        model=model,
        serial=serial,
        transport=transport,
        removable=removable,
        size_bytes=size_bytes,
        sysfs_path=Path(f"/sys/class/block/{device}"),
    )


class FakeInventory:
    def __init__(self):
        self._devices = [
            StorageDevice(
                drive=make_drive("sdb", "SERIAL1"),
                category="front-bay",
                label="Bay 1",
                physical_bay=1,
                kernel_slot=0,
                enclosure="6:0:0:0",
                mapping_source="kernel",
            ),
            StorageDevice(
                drive=make_drive("sdf", "SERIAL5"),
                category="front-bay",
                label="Bay 5",
                physical_bay=5,
                kernel_slot=4,
                enclosure="6:0:0:0",
                mapping_source="configured",
            ),
            StorageDevice(
                drive=make_drive(
                    "nvme0n1",
                    "NVME1",
                    model="Samsung SSD",
                    transport="nvme",
                    size_bytes=1_000_000_000_000,
                ),
                category="internal-nvme",
                label="Internal NVMe 1",
            ),
            StorageDevice(
                drive=make_drive(
                    "sde",
                    "BOOT1",
                    model="USB Disk Module",
                    transport="usb",
                    removable=True,
                    size_bytes=16_000_000_000,
                ),
                category="boot-media",
                label="Boot Media",
            ),
        ]

        self._bays = [
            FakeBay(
                physical_bay=1,
                kernel_slot=0,
                installed=True,
                status="OK",
                device="sdb",
                model="ST8000NE001",
                serial="SERIAL1",
                wwid="naa.test1",
                enclosure="6:0:0:0",
                mapping_source="kernel",
            ),
            FakeBay(
                physical_bay=5,
                kernel_slot=4,
                installed=True,
                status="configured",
                device="sdf",
                model="ST8000NE001",
                serial="SERIAL5",
                wwid="",
                enclosure="6:0:0:0",
                mapping_source="configured",
            ),
        ]

    def devices(self):
        return list(self._devices)

    def front_bays(self):
        return list(self._bays)


class FakeHardwareManager:
    def __init__(self):
        self.inventory = FakeInventory()

    def registered(self):
        return (
            "a125",
            "buzzer",
            "enclosure",
            "inventory",
            "topology",
        )

    def loaded(self):
        return ("enclosure", "inventory", "topology")


def build_test_parser():
    parser = argparse.ArgumentParser()
    subcommands = parser.add_subparsers(dest="command")
    add_hardware_subcommands(subcommands)
    return parser


def test_storage_report_contains_complete_inventory():
    report = build_storage_report(FakeHardwareManager())

    assert report["device_count"] == 4
    assert report["category_counts"] == {
        "front_bay": 2,
        "internal_nvme": 1,
        "boot_media": 1,
        "unassigned": 0,
    }

    assert report["devices"][0]["label"] == "Bay 1"
    assert report["devices"][1]["mapping_source"] == "configured"
    assert report["devices"][3]["serial"] == "BOOT1"


def test_topology_report_preserves_kernel_and_physical_slots():
    report = build_topology_report(FakeHardwareManager())

    assert report["bay_count"] == 2
    assert report["installed_count"] == 2
    assert report["configured_count"] == 1

    assert report["bays"][0]["physical_bay"] == 1
    assert report["bays"][0]["kernel_slot"] == 0
    assert report["bays"][1]["physical_bay"] == 5
    assert report["bays"][1]["kernel_slot"] == 4


def test_summary_report_contains_controller_state():
    report = build_summary_report(FakeHardwareManager())

    assert report["storage"]["device_count"] == 4
    assert report["topology"]["installed_count"] == 2
    assert "inventory" in report["controllers"]["registered"]
    assert "topology" in report["controllers"]["loaded"]


def test_hardware_summary_human_output(capsys):
    parser = build_test_parser()
    args = parser.parse_args(["hardware"])

    handled = handle_hardware_command(
        args,
        manager=FakeHardwareManager(),
    )
    output = capsys.readouterr().out

    assert handled is True
    assert "TruePanel Hardware" in output
    assert "Front Bays    : 2" in output
    assert "Internal NVMe : 1" in output
    assert "Boot Media    : 1" in output


def test_storage_human_output(capsys):
    parser = build_test_parser()
    args = parser.parse_args(["hardware", "storage"])

    handle_hardware_command(
        args,
        manager=FakeHardwareManager(),
    )
    output = capsys.readouterr().out

    assert "TruePanel Storage Inventory" in output
    assert "Bay 1" in output
    assert "/dev/sdb" in output
    assert "Internal NVMe 1" in output
    assert "Boot Media" in output


def test_storage_verbose_output(capsys):
    parser = build_test_parser()
    args = parser.parse_args(
        ["hardware", "storage", "--verbose"]
    )

    handle_hardware_command(
        args,
        manager=FakeHardwareManager(),
    )
    output = capsys.readouterr().out

    assert "Model     : ST8000NE001" in output
    assert "Transport : sata" in output
    assert "Enclosure : 6:0:0:0" in output


def test_storage_json_output(capsys):
    parser = build_test_parser()
    args = parser.parse_args(
        ["hardware", "storage", "--json"]
    )

    handle_hardware_command(
        args,
        manager=FakeHardwareManager(),
    )
    payload = json.loads(capsys.readouterr().out)

    assert payload["device_count"] == 4
    assert payload["devices"][0]["device_path"] == "/dev/sdb"
    assert payload["devices"][1]["physical_bay"] == 5
    assert payload["devices"][3]["serial"] == "BOOT1"


def test_topology_human_output(capsys):
    parser = build_test_parser()
    args = parser.parse_args(["hardware", "topology"])

    handle_hardware_command(
        args,
        manager=FakeHardwareManager(),
    )
    output = capsys.readouterr().out

    assert "TruePanel Storage Topology" in output
    assert "Bay 1" in output
    assert "Slot 0" in output
    assert "Bay 5" in output
    assert "configured" in output


def test_topology_json_output(capsys):
    parser = build_test_parser()
    args = parser.parse_args(
        ["hardware", "topology", "--json"]
    )

    handle_hardware_command(
        args,
        manager=FakeHardwareManager(),
    )
    payload = json.loads(capsys.readouterr().out)

    assert payload["bay_count"] == 2
    assert payload["configured_count"] == 1
    assert payload["bays"][1]["mapping_source"] == "configured"


def test_non_hardware_command_is_not_handled():
    args = argparse.Namespace(command="version")

    assert handle_hardware_command(
        args,
        manager=FakeHardwareManager(),
    ) is False
