from __future__ import annotations

import os
from pathlib import Path

from truepanel.loadmaster.config import load_settings
from truepanel.loadmaster.dock import Device, Docked
from truepanel.loadmaster.identity import folder_keys, library_index
from truepanel.loadmaster.plan import build_plan
from truepanel.loadmaster.scan import scan
from truepanel.loadmaster.selftest import SCRATCH, run_selftest
from truepanel.loadmaster.state import DriveRecord, StateStore

T = 1_700_000_000_000_000_000


def put(root: Path, rel: str, data: bytes) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    os.utime(path, ns=(T, T))


class FakeDock:
    """The drive is a folder; mount state is tracked, calls recorded."""

    def __init__(self, mount: Path, docked: list[Docked], state: str = "UNMOUNTED"):
        self.mount, self.docked, self.state, self.calls = mount, docked, state, []

    def scan(self):
        return list(self.docked)

    def mountpoint(self, docked):
        return self.mount

    def mount_state(self, docked):
        return self.state

    def mount_ro(self, docked):
        self.calls.append("ro")
        self.state = "RO"
        return self.mount

    def mount_rw(self, docked):
        self.calls.append("rw")
        self.state = "RW"
        return self.mount

    def release(self, docked):
        self.calls.append("release")
        self.state = "UNMOUNTED"


def setup(tmp_path, *, known=True):
    nas = tmp_path / "nas" / "TV A-M"
    usb_mount = tmp_path / "usb"
    put(nas, "Show (2020)/S01E01.mkv", b"one")
    put(usb_mount, "TV A-M/Show (2020)/S01E01.mkv", b"one")
    settings = load_settings(
        {
            "loadmaster": {
                "enabled": True,
                "state_dir": str(tmp_path / "state"),
                "drives": [{"name": "TV A-M", "nas_path": str(nas)}],
            }
        }
    )
    if known:
        store = StateStore(settings.state_dir)
        store.save_record(
            "tv-a-m",
            DriveRecord(name="TV A-M", uuid="U1", last_sync=1.0, files=scan(nas).files),
        )
    device = Device("/dev/sda2", "U1", "exfat", "TV A-M", "SER", True, 1, ())
    docked = Docked(settings.drives[0], device)
    return settings, docked, usb_mount, nas


def service_plan(settings, usb_mount, nas):
    drive = settings.drives[0]
    record = StateStore(settings.state_dir).load_record(drive.key, drive.name)
    usb_root = drive.usb_root(usb_mount)
    return build_plan(
        drive_name=drive.name,
        nas=scan(nas).files,
        usb=scan(usb_root).files,
        record=record.files if record.known else None,
        usb_fstype="exfat",
        library=library_index([(drive.name, drive.nas_path)]),
        usb_folders=folder_keys(usb_root),
    )


def running(plan):
    return lambda: {
        "available": True,
        "state": plan["state"],
        "message": "Movies up to date.",
        "drive": {"name": "TV A-M"},
        "plan": {"digest": plan["digest"]},
        "button": "ready",
        "servarr": {"sonarr": "ok", "radarr": "ok"},
    }


def results(report):
    return {c.name: c.result for c in report.checks}


def test_live_checks_agree_with_the_running_service(tmp_path):
    settings, docked, usb_mount, nas = setup(tmp_path)
    plan = service_plan(settings, usb_mount, nas)
    dock = FakeDock(usb_mount, [docked], state="RO")
    report = run_selftest(settings, dock=dock, status=running(plan))
    assert results(report) == {
        "config": "PASS",
        "records": "PASS",
        "library": "PASS",
        "detection": "PASS",
        "service": "PASS",
        "copy button": "PASS",
        "sonarr/radarr": "PASS",
        "plan agreement": "PASS",
        "capacity": "PASS",
    }
    assert not report.failed and dock.calls == []  # read-only: never mounted

    put(nas, "Show (2020)/S01E02.mkv", b"two")  # Sonarr import since planning
    report = run_selftest(settings, dock=dock, status=running(plan))
    assert results(report)["plan agreement"] == "WARN"


def test_hardware_checks_refuse_while_the_service_runs(tmp_path):
    settings, docked, usb_mount, nas = setup(tmp_path)
    plan = service_plan(settings, usb_mount, nas)
    dock = FakeDock(usb_mount, [docked], state="RO")
    report = run_selftest(settings, hardware=True, dock=dock, status=running(plan))
    skipped = [c for c in report.checks if c.result == "SKIP"]
    assert [c.name for c in skipped] == ["drive write test", "copy button"]
    assert dock.calls == []


class Reader:
    def __init__(self):
        self.closed = False

    def read_level(self):
        return 1

    def close(self):
        self.closed = True


def test_hardware_checks_with_the_service_stopped(tmp_path):
    settings, docked, usb_mount, nas = setup(tmp_path, known=False)
    dock = FakeDock(usb_mount, [docked])
    reader = Reader()
    report = run_selftest(
        settings,
        hardware=True,
        dock=dock,
        status=lambda: {"available": False, "message": "Loadmaster is not running."},
        button_reader_factory=lambda: reader,
    )
    got = results(report)
    assert got["service"] == "WARN" and got["records"] == "WARN"
    assert got["drive write test"] == "PASS" and got["copy button"] == "PASS"
    assert "released" in next(
        c.detail for c in report.checks if c.name == "copy button"
    )
    assert dock.calls == ["ro", "rw", "release"] and reader.closed
    assert not (usb_mount / "TV A-M" / SCRATCH).exists()
    assert scan(usb_mount / "TV A-M").files.keys() == {"Show (2020)/S01E01.mkv"}


def test_unreadable_button_fails(tmp_path):
    settings, docked, usb_mount, nas = setup(tmp_path)

    def broken():
        raise RuntimeError("unexpected Fintek chip id 0x0000")

    report = run_selftest(
        settings,
        hardware=True,
        dock=FakeDock(usb_mount, []),
        status=lambda: {"available": False},
        button_reader_factory=broken,
    )
    assert results(report)["copy button"] == "FAIL" and report.failed


def test_unknown_usb_labels_are_reported(tmp_path):
    settings, docked, usb_mount, nas = setup(tmp_path)
    devices = [
        Device("/dev/sdb2", "U9", "exfat", "Untitled", "S9", True, 1, ()),
        Device("/dev/sdd2", "E1", "vfat", "EFI", "S8", True, 1, ()),
        Device("/dev/sdc1", "Z1", "zfs_member", "HDDs", "S7", False, 1, ()),
    ]
    report = run_selftest(
        settings,
        dock=FakeDock(usb_mount, []),
        status=lambda: {"available": False},
        usb_devices=lambda: devices,
    )
    unknown = next(c for c in report.checks if c.name == "unknown USB drives")
    assert unknown.result == "WARN" and "Untitled on /dev/sdb2" in unknown.detail
    assert "EFI" not in unknown.detail and "HDDs" not in unknown.detail
