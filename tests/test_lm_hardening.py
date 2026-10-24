"""Safety regression tests for Loadmaster v2 release hardening."""

import errno
import os
from pathlib import Path

import pytest

from truepanel.loadmaster import transfer
from truepanel.loadmaster.plan import DELETE_USB, TO_USB, build_plan
from truepanel.loadmaster.scan import Fingerprint, scan


@pytest.mark.parametrize("dirname", ["Daria", "daria", "Daria (1997)"])
def test_daria_restoration_never_enters_scan(tmp_path: Path, dirname: str):
    guarded = tmp_path / dirname
    guarded.mkdir()
    (guarded / "episode.mkv").write_bytes(b"protected")
    (tmp_path / "safe.mkv").write_bytes(b"ok")
    tree = scan(tmp_path)
    assert set(tree.files) == {"safe.mkv"}
    assert (guarded / "episode.mkv").read_bytes() == b"protected"


def test_external_inventory_cannot_plan_daria_changes():
    old = Fingerprint(4, 1_700_000_000_000_000_000)
    plan = build_plan(
        drive_name="TV N-Z",
        nas={"Daria (1997)/S01E01.mkv": old, "Other/show.mkv": old},
        usb={"Daria (1997)/S01E01.mkv": Fingerprint(5, old.mtime_ns)},
        record={"Daria (1997)/S01E01.mkv": old},
    )
    assert all("daria" not in item["path"].casefold() for item in plan["actions"])
    assert any(item["path"] == "Other/show.mkv" for item in plan["actions"])


def test_new_files_copied_before_usb_deletions():
    old = Fingerprint(3, 1_700_000_000_000_000_000)
    plan = build_plan(
        drive_name="TV N-Z",
        nas={"new.mkv": old},
        usb={"old.mkv": old},
        record={"old.mkv": old},
    )
    assert [a["op"] for a in plan["actions"]] == [TO_USB, DELETE_USB]


def test_no_replace_unsupported_never_uses_racy_rename(tmp_path, monkeypatch):
    source = tmp_path / "partial"
    dest = tmp_path / "target"
    source.write_bytes(b"source")
    dest.write_bytes(b"existing")
    monkeypatch.setattr(transfer, "_renameat2", False)
    def forbidden(*args):
        raise AssertionError("os.rename must never be used as a fallback")
    monkeypatch.setattr(transfer.os, "rename", forbidden)
    with pytest.raises(transfer.ItemError, match="ATOMIC_NOREPLACE_UNSUPPORTED"):
        transfer._noreplace_rename(source, dest)
    assert source.read_bytes() == b"source"
    assert dest.read_bytes() == b"existing"
