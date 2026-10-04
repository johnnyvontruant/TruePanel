import json
import os
from pathlib import Path

import pytest

from truepanel.cargo.cartridges import (
    CartridgeDefinition,
)
from truepanel.cargo.loadmaster import (
    FileFingerprint,
    LoadmasterPlanError,
    build_sync_plan,
    inventory_payload,
    load_inventory,
    scan_tree,
)


def cartridge(tmp_path):
    return CartridgeDefinition(
        cartridge_id="movies-e-i",
        label="Movies E-I",
        uuid="ABCD-1234",
        role="movies",
        source_prefix=tmp_path / "nas",
        usb_relative_path=Path(
            "Movies E-I"
        ),
        allow_ingest=True,
        allow_backup=True,
        delete_policy="never",
    )


def prepare(tmp_path):
    item = cartridge(tmp_path)
    item.source_prefix.mkdir()

    mount = tmp_path / "usb"
    usb_root = mount / "Movies E-I"
    usb_root.mkdir(parents=True)

    return item, mount, usb_root


def write_file(path, content, mtime_ns):
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    path.write_bytes(content)
    os.utime(
        path,
        ns=(mtime_ns, mtime_ns),
    )


def test_new_nas_file_plans_backup(
    tmp_path,
):
    item, mount, _ = prepare(tmp_path)

    write_file(
        item.source_prefix / "Heat.mkv",
        b"123",
        1_000_000_000,
    )

    plan = build_sync_plan(
        cartridge=item,
        usb_mount=mount,
    )

    assert plan["state"] == "READY"
    assert (
        plan["summary"]["backup_files"]
        == 1
    )
    assert (
        plan["actions"][0]["direction"]
        == "NAS_TO_USB"
    )
    assert (
        plan["actions"][0]["reason"]
        == "NEW_ON_NAS"
    )


def test_new_usb_file_plans_ingest(
    tmp_path,
):
    item, mount, usb_root = (
        prepare(tmp_path)
    )

    write_file(
        usb_root / "Heat.mkv",
        b"123",
        1_000_000_000,
    )

    plan = build_sync_plan(
        cartridge=item,
        usb_mount=mount,
    )

    assert plan["state"] == "READY"
    assert (
        plan["summary"]["ingest_files"]
        == 1
    )
    assert (
        plan["actions"][0]["direction"]
        == "USB_TO_NAS"
    )
    assert (
        plan["actions"][0]["reason"]
        == "NEW_ON_USB"
    )


def test_exfat_timestamp_window_is_clear(
    tmp_path,
):
    item, mount, usb_root = (
        prepare(tmp_path)
    )

    write_file(
        item.source_prefix / "Heat.mkv",
        b"123",
        5_000_000_000,
    )
    write_file(
        usb_root / "Heat.mkv",
        b"123",
        6_500_000_000,
    )

    plan = build_sync_plan(
        cartridge=item,
        usb_mount=mount,
    )

    assert plan["state"] == "CLEAR"
    assert (
        plan["summary"]["unchanged_files"]
        == 1
    )


def test_divergent_without_baseline_holds(
    tmp_path,
):
    item, mount, usb_root = (
        prepare(tmp_path)
    )

    write_file(
        item.source_prefix / "Heat.mkv",
        b"123",
        1_000_000_000,
    )
    write_file(
        usb_root / "Heat.mkv",
        b"1234",
        1_000_000_000,
    )

    plan = build_sync_plan(
        cartridge=item,
        usb_mount=mount,
    )

    assert plan["state"] == "HOLD"
    assert (
        plan["conflicts"][0]["reason"]
        == "DIVERGENT_WITHOUT_BASELINE"
    )


def test_nas_changed_from_baseline_plans_backup(
    tmp_path,
):
    item, mount, usb_root = (
        prepare(tmp_path)
    )

    write_file(
        item.source_prefix / "Heat.mkv",
        b"new",
        20_000_000_000,
    )
    write_file(
        usb_root / "Heat.mkv",
        b"old",
        10_000_000_000,
    )

    baseline = {
        "Heat.mkv": FileFingerprint(
            size_bytes=3,
            mtime_ns=10_000_000_000,
        )
    }

    plan = build_sync_plan(
        cartridge=item,
        usb_mount=mount,
        inventory=baseline,
    )

    assert plan["state"] == "READY"
    assert (
        plan["actions"][0]["direction"]
        == "NAS_TO_USB"
    )
    assert (
        plan["actions"][0]["reason"]
        == "NAS_UPDATED"
    )


def test_usb_changed_from_baseline_plans_ingest(
    tmp_path,
):
    item, mount, usb_root = (
        prepare(tmp_path)
    )

    write_file(
        item.source_prefix / "Heat.mkv",
        b"old",
        10_000_000_000,
    )
    write_file(
        usb_root / "Heat.mkv",
        b"new",
        20_000_000_000,
    )

    baseline = {
        "Heat.mkv": FileFingerprint(
            size_bytes=3,
            mtime_ns=10_000_000_000,
        )
    }

    plan = build_sync_plan(
        cartridge=item,
        usb_mount=mount,
        inventory=baseline,
    )

    assert plan["state"] == "READY"
    assert (
        plan["actions"][0]["direction"]
        == "USB_TO_NAS"
    )
    assert (
        plan["actions"][0]["reason"]
        == "USB_UPDATED"
    )


def test_both_sides_changed_holds(
    tmp_path,
):
    item, mount, usb_root = (
        prepare(tmp_path)
    )

    write_file(
        item.source_prefix / "Heat.mkv",
        b"nas-new",
        20_000_000_000,
    )
    write_file(
        usb_root / "Heat.mkv",
        b"usb-newer",
        30_000_000_000,
    )

    baseline = {
        "Heat.mkv": FileFingerprint(
            size_bytes=3,
            mtime_ns=10_000_000_000,
        )
    }

    plan = build_sync_plan(
        cartridge=item,
        usb_mount=mount,
        inventory=baseline,
    )

    assert plan["state"] == "HOLD"
    assert (
        plan["conflicts"][0]["reason"]
        == "BOTH_SIDES_CHANGED"
    )


def test_missing_on_nas_since_last_sync_holds(
    tmp_path,
):
    item, mount, usb_root = (
        prepare(tmp_path)
    )

    write_file(
        usb_root / "Heat.mkv",
        b"old",
        10_000_000_000,
    )

    baseline = {
        "Heat.mkv": FileFingerprint(
            size_bytes=3,
            mtime_ns=10_000_000_000,
        )
    }

    plan = build_sync_plan(
        cartridge=item,
        usb_mount=mount,
        inventory=baseline,
    )

    assert plan["state"] == "HOLD"
    assert (
        plan["conflicts"][0]["reason"]
        == "MISSING_ON_NAS_SINCE_LAST_SYNC"
    )


def test_scan_rejects_symlink(
    tmp_path,
):
    root = tmp_path / "root"
    root.mkdir()

    target = tmp_path / "target"
    target.write_text(
        "x",
        encoding="utf-8",
    )

    (
        root / "link"
    ).symlink_to(target)

    with pytest.raises(
        LoadmasterPlanError,
        match="symlink",
    ):
        scan_tree(root)


def test_inventory_roundtrip(
    tmp_path,
):
    item, _, _ = prepare(tmp_path)

    write_file(
        item.source_prefix / "Heat.mkv",
        b"123",
        10_000_000_000,
    )

    files = scan_tree(
        item.source_prefix
    )

    payload = inventory_payload(
        cartridge=item,
        files=files,
        captured_at=(
            "2026-10-02T22:00:00Z"
        ),
    )

    path = tmp_path / "inventory.json"
    path.write_text(
        json.dumps(payload),
        encoding="utf-8",
    )

    loaded = load_inventory(
        path,
        cartridge_id=(
            item.cartridge_id
        ),
    )

    assert loaded == files



def test_scan_ignores_sdr_rescue_work_files(
    tmp_path,
):
    root = tmp_path / "root"
    root.mkdir()

    write_file(
        root / "Collateral (2004).mkv",
        b"canonical",
        10_000_000_000,
    )
    write_file(
        root / (
            "Collateral (2004).mkv."
            "sdr-rescue-backup-20261003-201244"
        ),
        b"rollback",
        10_000_000_000,
    )
    write_file(
        root / (
            ".Collateral (2004).mkv."
            "sdr-rescue-partial"
        ),
        b"partial",
        10_000_000_000,
    )
    write_file(
        root / (
            "Collateral (2004).mkv."
            "failed-sdr-rescue"
        ),
        b"failed",
        10_000_000_000,
    )

    files = scan_tree(root)

    assert set(files) == {
        "Collateral (2004).mkv",
    }


def test_sdr_rollback_file_never_plans_usb_backup(
    tmp_path,
):
    item, mount, usb_root = prepare(tmp_path)

    canonical = "Collateral (2004)/Collateral (2004).mkv"
    rollback = (
        "Collateral (2004)/"
        "Collateral (2004).mkv."
        "sdr-rescue-backup-20261003-201244"
    )

    write_file(
        item.source_prefix / canonical,
        b"new-sdr",
        20_000_000_000,
    )
    write_file(
        item.source_prefix / rollback,
        b"old-hdr",
        10_000_000_000,
    )
    write_file(
        usb_root / canonical,
        b"old-hdr",
        10_000_000_000,
    )

    baseline = {
        canonical: FileFingerprint(
            size_bytes=7,
            mtime_ns=10_000_000_000,
        )
    }

    plan = build_sync_plan(
        cartridge=item,
        usb_mount=mount,
        inventory=baseline,
    )

    assert plan["state"] == "READY"
    assert plan["summary"]["backup_files"] == 1
    assert len(plan["actions"]) == 1
    assert plan["actions"][0]["relative_path"] == canonical
    assert plan["actions"][0]["direction"] == "NAS_TO_USB"
    assert plan["actions"][0]["reason"] == "NAS_UPDATED"
