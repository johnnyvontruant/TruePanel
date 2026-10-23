from __future__ import annotations

import json
from pathlib import Path

import pytest

from truepanel.cargo.cartridges import CartridgeDefinition
from truepanel.cargo.dock import (
    MOUNT_OPTIONS_RO,
    CartridgeDock,
    LoadmasterDockError,
    parse_lsblk,
)


def cartridge(**overrides) -> CartridgeDefinition:
    payload = {
        "cartridge_id": "movies-e-i",
        "label": "Movies E-I",
        "uuid": "6989-100A",
        "role": "movies",
        "source_prefix": Path("/mnt/HDDs/Movies/Movies E-I"),
        "usb_relative_path": Path("Movies E-I"),
    }
    payload.update(overrides)
    return CartridgeDefinition(**payload)


def lsblk(*disks: dict) -> str:
    return json.dumps({"blockdevices": list(disks)})


def usb_disk(uuid: str = "6989-100A", serial: str = "2532EA8D3ED1", **part) -> dict:
    child = {
        "name": "sdh1",
        "path": "/dev/sdh1",
        "type": "part",
        "uuid": uuid,
        "fstype": "exfat",
        "label": "MOVIES",
        "serial": None,
        "tran": None,
        "rm": False,
        "hotplug": True,
        "mountpoints": [None],
        "size": 5_000_000_000_000,
    }
    child.update(part)
    return {
        "name": "sdh",
        "path": "/dev/sdh",
        "type": "disk",
        "serial": serial,
        "tran": "usb",
        "rm": False,
        "hotplug": True,
        "children": [child],
    }


class Runner:
    def __init__(self, lsblk_output: str) -> None:
        self.lsblk_output = lsblk_output
        self.calls: list[list[str]] = []

    def __call__(self, argv):
        self.calls.append(list(argv))
        if argv[0] == "lsblk":
            return self.lsblk_output
        return ""


def test_parse_lsblk_inherits_disk_serial_and_transport():
    devices = parse_lsblk(lsblk(usb_disk()))

    assert len(devices) == 1
    assert devices[0].path == "/dev/sdh1"
    assert devices[0].serial == "2532EA8D3ED1"
    assert devices[0].transport == "usb"
    assert devices[0].mountpoints == ()


def test_scan_identifies_registered_usb_cartridge(tmp_path):
    dock = CartridgeDock(
        cartridges=[cartridge()],
        mount_root=tmp_path / "mnt",
        runner=Runner(lsblk(usb_disk())),
        mountinfo_reader=lambda: "",
    )

    scan = dock.scan()

    assert scan.state == "DOCKED"
    assert scan.docked[0].identity_verified
    assert scan.docked[0].identity_reason == "UUID_ONLY"


def test_scan_ignores_registered_uuid_on_non_usb_disk(tmp_path):
    disk = usb_disk()
    disk["tran"] = "sata"
    dock = CartridgeDock(
        cartridges=[cartridge()],
        mount_root=tmp_path,
        runner=Runner(lsblk(disk)),
        mountinfo_reader=lambda: "",
    )

    assert dock.scan().state == "EMPTY"


def test_pinned_serial_mismatch_is_unverified(tmp_path):
    dock = CartridgeDock(
        cartridges=[cartridge(device_serial="OTHER")],
        mount_root=tmp_path,
        runner=Runner(lsblk(usb_disk())),
        mountinfo_reader=lambda: "",
    )

    docked = dock.scan().docked[0]
    assert not docked.identity_verified
    assert docked.identity_reason == "DEVICE_SERIAL_MISMATCH"

    with pytest.raises(LoadmasterDockError):
        dock.mount_read_only(docked)


def test_two_cartridges_is_multiple(tmp_path):
    other = usb_disk(uuid="AAAA-BBBB", serial="X2", path="/dev/sdi1", name="sdi1")
    other["path"] = "/dev/sdi"
    dock = CartridgeDock(
        cartridges=[
            cartridge(),
            cartridge(
                cartridge_id="tv-a-m",
                label="TV A-M",
                uuid="AAAA-BBBB",
                role="tv",
                source_prefix=Path("/mnt/HDDs/Shows/TV A-M"),
                usb_relative_path=Path("TV A-M"),
            ),
        ],
        mount_root=tmp_path,
        runner=Runner(lsblk(usb_disk(), other)),
        mountinfo_reader=lambda: "",
    )

    assert dock.scan().state == "MULTIPLE"


def test_mount_read_only_uses_restrictive_options(tmp_path):
    runner = Runner(lsblk(usb_disk()))
    dock = CartridgeDock(
        cartridges=[cartridge()],
        mount_root=tmp_path / "mnt",
        runner=runner,
        mountinfo_reader=lambda: "",
    )
    docked = dock.scan().docked[0]

    mountpoint = dock.mount_read_only(docked)

    assert mountpoint == tmp_path / "mnt" / "movies-e-i"
    assert mountpoint.is_dir()
    assert runner.calls[-1] == [
        "mount",
        "-t",
        "exfat",
        "-o",
        MOUNT_OPTIONS_RO,
        "/dev/sdh1",
        str(mountpoint),
    ]


def test_mount_refuses_foreign_mount(tmp_path):
    dock = CartridgeDock(
        cartridges=[cartridge()],
        mount_root=tmp_path / "mnt",
        runner=Runner(lsblk(usb_disk(mountpoints=["/media/usb0"]))),
        mountinfo_reader=lambda: "",
    )
    docked = dock.scan().docked[0]

    assert dock.mount_state(docked) == "FOREIGN"
    with pytest.raises(LoadmasterDockError, match="does not own"):
        dock.mount_read_only(docked)


def test_remount_and_release_owned_mount(tmp_path):
    mountpoint = tmp_path / "mnt" / "movies-e-i"
    mountinfo = {"text": ""}
    runner = Runner(lsblk(usb_disk()))
    dock = CartridgeDock(
        cartridges=[cartridge()],
        mount_root=tmp_path / "mnt",
        runner=runner,
        mountinfo_reader=lambda: mountinfo["text"],
    )
    docked = dock.scan().docked[0]
    dock.mount_read_only(docked)

    mountinfo["text"] = (
        f"90 30 8:113 / {mountpoint} ro,nosuid,nodev,noexec,noatime - exfat /dev/sdh1 ro\n"
    )
    assert dock.mount_state(docked) == "MOUNTED_RO"

    dock.remount_read_write(docked)
    assert runner.calls[-1][:3] == [
        "mount",
        "-o",
        "remount,rw,nosuid,nodev,noexec,noatime",
    ]

    mountinfo["text"] = mountinfo["text"].replace(" ro,nosuid", " rw,nosuid")
    assert dock.mount_state(docked) == "MOUNTED_RW"

    dock.release(docked)
    assert runner.calls[-2] == ["sync"]
    assert runner.calls[-1] == ["umount", str(mountpoint)]


def test_mountpoint_with_stray_files_is_refused(tmp_path):
    mountpoint = tmp_path / "mnt" / "movies-e-i"
    mountpoint.mkdir(parents=True)
    (mountpoint / "stray").write_text("x")
    dock = CartridgeDock(
        cartridges=[cartridge()],
        mount_root=tmp_path / "mnt",
        runner=Runner(lsblk(usb_disk())),
        mountinfo_reader=lambda: "",
    )

    with pytest.raises(LoadmasterDockError, match="not empty"):
        dock.mount_read_only(dock.scan().docked[0])
