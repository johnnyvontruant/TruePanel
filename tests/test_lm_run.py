from __future__ import annotations

import os
import threading
from pathlib import Path, PurePosixPath

import pytest

from truepanel.loadmaster import run as run_module
from truepanel.loadmaster import transfer
from truepanel.loadmaster.config import Drive
from truepanel.loadmaster.plan import build_plan
from truepanel.loadmaster.run import RunContext, execute
from truepanel.loadmaster.scan import Fingerprint, scan
from truepanel.loadmaster.state import DriveRecord, StateStore

T = 1_700_000_000_000_000_000
HOUR = 3600 * 10**9


class Rig:
    def __init__(self, tmp: Path) -> None:
        self.drive = Drive("TV A-M", tmp / "nas" / "TV A-M", "TV A-M")
        self.nas = self.drive.nas_path
        self.usb = tmp / "usb" / "TV A-M"
        self.nas.mkdir(parents=True)
        self.usb.mkdir(parents=True)
        self.store = StateStore(tmp / "state")
        self.record = DriveRecord(name=self.drive.name)

    @staticmethod
    def put(root: Path, rel: str, data: bytes, mtime: int = T) -> Path:
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        os.utime(path, ns=(mtime, mtime))
        return path

    def plan(self, usb_fstype=None):
        return build_plan(
            drive_name=self.drive.name,
            nas=scan(self.nas).files,
            usb=scan(self.usb).files,
            record=self.record.files if self.record.known else None,
            usb_fstype=usb_fstype,
        )

    def sync(self, plan=None, **kwargs):
        plan = plan or self.plan()
        return execute(
            RunContext(self.drive, self.usb, plan, self.record, self.store, **kwargs)
        )


@pytest.fixture
def rig(tmp_path):
    return Rig(tmp_path)


def test_first_sync_then_clear(rig):
    rig.put(rig.nas, "Show/S01E01.mkv", b"one")
    rig.put(rig.usb, "Other/S01E01.mkv", b"two")
    rig.put(rig.nas, "Same/x.nfo", b"same")
    rig.put(rig.usb, "Same/x.nfo", b"same")

    receipt = rig.sync()

    assert receipt["state"] == "COMPLETE"
    assert (rig.usb / "Show/S01E01.mkv").read_bytes() == b"one"
    assert (rig.nas / "Other/S01E01.mkv").read_bytes() == b"two"
    assert (rig.usb / "Show/S01E01.mkv").stat().st_mtime_ns == T
    assert rig.record.known
    assert set(rig.record.files) == {
        "Show/S01E01.mkv",
        "Other/S01E01.mkv",
        "Same/x.nfo",
    }
    assert rig.plan()["state"] == "CLEAR"
    # Record survives a restart.
    reloaded = rig.store.load_record(rig.drive.key, rig.drive.name)
    assert reloaded.files == rig.record.files


def test_case_renamed_episode_updates_in_place_on_both_sides(rig):
    rig.put(rig.nas, "Show/1x01.mkv", b"old")
    rig.put(rig.usb, "Show/1X01.mkv", b"old")
    assert rig.sync(rig.plan("exfat"))["state"] == "COMPLETE"
    assert set(rig.record.files) == {"Show/1x01.mkv"}

    # Updated on the NAS: the drive's own file is replaced, never doubled.
    rig.put(rig.nas, "Show/1x01.mkv", b"new on nas", T + HOUR)
    assert rig.sync(rig.plan("exfat"))["state"] == "COMPLETE"
    assert {p.name for p in (rig.usb / "Show").iterdir()} == {"1X01.mkv"}
    assert (rig.usb / "Show/1X01.mkv").read_bytes() == b"new on nas"

    # Updated on the drive: the NAS file keeps the NAS name.
    rig.put(rig.usb, "Show/1X01.mkv", b"new on usb!", T + 2 * HOUR)
    assert rig.sync(rig.plan("exfat"))["state"] == "COMPLETE"
    nas_names = {
        p.name for p in (rig.nas / "Show").iterdir() if not p.name.startswith(".")
    }
    assert nas_names == {"1x01.mkv"}
    assert (rig.nas / "Show/1x01.mkv").read_bytes() == b"new on usb!"
    assert rig.plan("exfat")["state"] == "CLEAR"


def test_radarr_upgrade_mirrors_and_prunes_empty_folder(rig):
    rig.put(rig.nas, "Heat (1995)/Heat 720p.mkv", b"old")
    rig.sync()
    (rig.nas / "Heat (1995)/Heat 720p.mkv").unlink()
    rig.put(rig.nas, "Heat (1995)/Heat 2160p.mkv", b"new!")
    rig.put(rig.nas, "Gone (2001)/x.mkv", b"g")
    rig.sync()
    (rig.nas / "Gone (2001)/x.mkv").unlink()
    (rig.nas / "Gone (2001)").rmdir()

    receipt = rig.sync()

    assert receipt["state"] == "COMPLETE"
    assert not (rig.usb / "Heat (1995)/Heat 720p.mkv").exists()
    assert (rig.usb / "Heat (1995)/Heat 2160p.mkv").read_bytes() == b"new!"
    assert not (rig.usb / "Gone (2001)").exists()
    assert rig.plan()["state"] == "CLEAR"


def test_laptop_upgrade_retires_nas_original_without_deleting(rig):
    rig.put(rig.nas, "Heat (1995)/Heat 720p.mkv", b"old")
    rig.sync()
    (rig.usb / "Heat (1995)/Heat 720p.mkv").unlink()
    rig.put(rig.usb, "Heat (1995)/Heat 2160p.mkv", b"laptop", T + HOUR)

    receipt = rig.sync()

    assert receipt["state"] == "COMPLETE"
    assert (rig.nas / "Heat (1995)/Heat 2160p.mkv").read_bytes() == b"laptop"
    assert not (rig.nas / "Heat (1995)/Heat 720p.mkv").exists()
    kept = list(rig.drive.replaced_dir.rglob("Heat 720p.mkv"))
    assert len(kept) == 1 and kept[0].read_bytes() == b"old"
    assert rig.plan()["state"] == "CLEAR"


def test_newer_same_name_on_usb_replaces_nas_and_keeps_old(rig):
    rig.put(rig.nas, "Elf (2003)/Elf.mkv", b"old")
    rig.sync()
    rig.put(rig.usb, "Elf (2003)/Elf.mkv", b"remastered", T + HOUR)

    receipt = rig.sync()

    assert receipt["results"][0]["reason"] == "UPDATED_ON_USB"
    assert (rig.nas / "Elf (2003)/Elf.mkv").read_bytes() == b"remastered"
    assert [p.read_bytes() for p in rig.drive.replaced_dir.rglob("Elf.mkv")] == [b"old"]


def test_failed_copy_keeps_nas_original(rig, monkeypatch):
    rig.put(rig.nas, "Heat (1995)/Heat 720p.mkv", b"old")
    rig.sync()
    (rig.usb / "Heat (1995)/Heat 720p.mkv").unlink()
    rig.put(rig.usb, "Heat (1995)/Heat 2160p.mkv", b"laptop")

    def broken(**kwargs):
        raise transfer.ItemError("VERIFY_HASH_MISMATCH", "simulated")

    monkeypatch.setattr(run_module, "copy_file", broken)
    receipt = rig.sync()

    assert receipt["state"] == "PARTIAL"
    assert [r["outcome"] for r in receipt["results"]] == ["FAILED", "SKIPPED"]
    assert (rig.nas / "Heat (1995)/Heat 720p.mkv").exists()
    # Same decision next time once the problem is gone.
    monkeypatch.undo()
    assert rig.sync()["state"] == "COMPLETE"
    assert (rig.nas / "Heat (1995)/Heat 2160p.mkv").exists()


def test_usb_file_changed_after_plan_is_not_deleted(rig):
    rig.put(rig.nas, "a.mkv", b"a")
    rig.put(rig.nas, "keep.mkv", b"k")
    rig.sync()
    (rig.nas / "a.mkv").unlink()
    plan = rig.plan()
    rig.put(rig.usb, "a.mkv", b"edited since", T + HOUR)

    receipt = rig.sync(plan)

    assert receipt["results"][0]["error"].startswith("CHANGED_SINCE_PLAN")
    assert (rig.usb / "a.mkv").read_bytes() == b"edited since"


def test_not_enough_space_changes_nothing(rig, monkeypatch):
    rig.put(rig.nas, "a.mkv", b"a" * 100)
    monkeypatch.setattr(run_module, "_free", lambda path: 0)

    receipt = rig.sync()

    assert receipt["state"] == "FAILED"
    assert "free space" in receipt["reason"]
    assert not (rig.usb / "a.mkv").exists()
    assert not rig.record.known


def test_device_error_stops_the_run(rig, monkeypatch):
    rig.put(rig.nas, "a.mkv", b"a")
    rig.put(rig.nas, "b.mkv", b"b")

    def unplugged(**kwargs):
        raise OSError(5, "Input/output error")

    monkeypatch.setattr(run_module, "copy_file", unplugged)
    receipt = rig.sync()

    assert receipt["state"] == "FAILED"
    assert [r["outcome"] for r in receipt["results"]] == ["FAILED", "NOT_ATTEMPTED"]


def test_activity_log_and_receipt_written(rig):
    rig.put(rig.nas, "a.mkv", b"a")
    receipt = rig.sync()

    log = rig.store.recent_activity()
    assert log[0]["kind"] == "run" and log[0]["state"] == "COMPLETE"
    assert log[1]["kind"] == "moved" and log[1]["path"] == "a.mkv"
    assert (rig.store.root / "receipts" / f"{receipt['id']}.json").exists()


# ------------------------------------------------------------- copy level


def _copy(src: Path, dest_root: Path, rel: str, stop, **kwargs):
    info = src.stat()
    return transfer.copy_file(
        source=src,
        dest_root=dest_root,
        rel=PurePosixPath(rel),
        expected=Fingerprint(info.st_size, info.st_mtime_ns),
        replace=False,
        stop=stop,
        **kwargs,
    )


def test_interrupted_copy_resumes(rig, monkeypatch):
    monkeypatch.setattr(transfer, "CHUNK", 256 * 1024)
    data = os.urandom(3 * 1024 * 1024)
    src = rig.put(rig.nas, "big.mkv", data)
    stop = threading.Event()
    seen = [0]

    def unplug(count):
        seen[0] += count
        if seen[0] >= 1024 * 1024:
            stop.set()

    with pytest.raises(transfer.Cancelled):
        _copy(src, rig.usb, "big.mkv", stop, on_bytes=unplug)
    partials = list(rig.usb.glob("*.loadmaster-partial"))
    assert len(partials) == 1 and not (rig.usb / "big.mkv").exists()
    kept = partials[0].stat().st_size
    assert kept >= 1024 * 1024

    result = _copy(src, rig.usb, "big.mkv", threading.Event())

    assert result.resumed_bytes == kept
    assert (rig.usb / "big.mkv").read_bytes() == data
    assert not list(rig.usb.glob("*.loadmaster-partial"))


def test_corrupt_partial_restarts(rig):
    src = rig.put(rig.nas, "x.mkv", os.urandom(4096))
    info = src.stat()
    partial = transfer.partial_path(
        rig.usb, PurePosixPath("x.mkv"), Fingerprint(info.st_size, info.st_mtime_ns)
    )
    partial.write_bytes(b"\0" * 100)

    result = _copy(src, rig.usb, "x.mkv", threading.Event())

    assert result.resumed_bytes == 0
    assert (rig.usb / "x.mkv").read_bytes() == src.read_bytes()


def test_last_instant_destination_is_never_overwritten(rig, monkeypatch):
    src = rig.put(rig.nas, "x.mkv", b"ours")
    target = rig.usb / "x.mkv"

    def intruder(fd):
        if not target.exists():
            target.write_bytes(b"theirs")

    monkeypatch.setattr(transfer, "_drop_cache", intruder)
    with pytest.raises(transfer.ItemError, match="DESTINATION_APPEARED"):
        _copy(src, rig.usb, "x.mkv", threading.Event())
    assert target.read_bytes() == b"theirs"


def test_unsafe_paths_rejected():
    for bad in ("", "/etc/passwd", "../x", "a/../b", "a//b"):
        with pytest.raises(transfer.ItemError):
            transfer.safe_relative(bad)


def test_scan_skips_mac_and_windows_clutter(tmp_path):
    keep = "Show/S01E01.mkv"
    clutter = [
        ".DS_Store",
        "Show/._S01E01.mkv",
        ".Spotlight-V100/Store-V2/index",
        ".Trashes/501/old.mkv",
        ".fseventsd/0000",
        "$RECYCLE.BIN/S-1-5/$R1.mkv",
        "System Volume Information/IndexerVolumeGuid",
        "Show/Thumbs.db",
        "Show/DESKTOP.INI",
        "Show/Icon\r",
        "Icon\uf00d",  # Icon\r as macOS stores it on exFAT (seen on TV N-Z)
        "__MACOSX/Show/._S01E01.mkv",
    ]
    for rel in [keep, *clutter]:
        Rig.put(tmp_path, rel, b"x")
    assert list(scan(tmp_path).files) == [keep]
