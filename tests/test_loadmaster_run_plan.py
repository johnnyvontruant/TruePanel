from __future__ import annotations

import os

from loadmaster_fixtures import MTIME, make_bay

from truepanel.cargo.run_plan import build_run_plan, physical_preflight


def plan(bay, *, backlog, baseline, ingest=True):
    return build_run_plan(
        cartridge=bay.cartridge,
        cartridges=[bay.cartridge],
        usb_mount=bay.usb_mount,
        backlog=backlog,
        inventory=baseline,
        ingest_enabled=ingest,
    )


def test_in_sync_cartridge_is_clear(tmp_path):
    bay = make_bay(tmp_path)
    bay.nas("Heat (1995)/Heat.mkv", b"heat")
    bay.usb("Heat (1995)/Heat.mkv", b"heat")

    result = plan(bay, backlog=bay.backlog(), baseline=bay.baseline())

    assert result["state"] == "CLEAR"
    assert result["actions"] == []


def test_backlog_item_becomes_backup_and_new_usb_file_becomes_ingest(tmp_path):
    bay = make_bay(tmp_path)
    bay.nas("Heat (1995)/Heat.mkv", b"heat")
    bay.usb("Heat (1995)/Heat.mkv", b"heat")
    baseline = bay.baseline()

    bay.nas("Inception (2010)/Inception.mkv", b"dream")
    bay.usb("Elf (2003)/Elf.mkv", b"buddy")

    result = plan(
        bay,
        backlog=bay.backlog("Inception (2010)/Inception.mkv"),
        baseline=baseline,
    )

    assert result["state"] == "READY"
    assert [
        (a["direction"], a["relative_path"], a["reason"]) for a in result["actions"]
    ] == [
        ("NAS_TO_USB", "Inception (2010)/Inception.mkv", "NEW_ON_NAS"),
        ("USB_TO_NAS", "Elf (2003)/Elf.mkv", "NEW_ON_USB"),
    ]
    assert result["summary"]["backup_bytes"] == 5
    assert result["summary"]["ingest_bytes"] == 5


def test_nas_file_outside_backlog_is_not_swept_onto_cartridge(tmp_path):
    bay = make_bay(tmp_path)
    baseline = bay.baseline()
    bay.nas("Inception (2010)/Inception.mkv", b"dream")

    result = plan(bay, backlog=bay.backlog(), baseline=baseline)

    assert result["state"] == "CLEAR"


def test_ingest_disabled_skips_usb_only_files(tmp_path):
    bay = make_bay(tmp_path)
    baseline = bay.baseline()
    bay.usb("Elf (2003)/Elf.mkv", b"buddy")

    result = plan(bay, backlog=bay.backlog(), baseline=baseline, ingest=False)

    assert result["state"] == "CLEAR"
    assert result["ingest_enabled"] is False


def test_retired_nas_file_is_a_notice_not_an_ingest(tmp_path):
    bay = make_bay(tmp_path)
    old = bay.nas("Heat (1995)/Heat.720p.mkv", b"old")
    bay.usb("Heat (1995)/Heat.720p.mkv", b"old")
    baseline = bay.baseline()
    old.unlink()  # Radarr upgraded and removed the old file

    result = plan(bay, backlog=bay.backlog(), baseline=baseline)

    assert result["state"] == "CLEAR"
    assert result["notices"] == [
        {"relative_path": "Heat (1995)/Heat.720p.mkv", "reason": "RETIRED_ON_NAS"}
    ]


def test_divergent_file_without_baseline_holds(tmp_path):
    bay = make_bay(tmp_path)
    bay.nas("Heat (1995)/Heat.mkv", b"nas-version")
    bay.usb("Heat (1995)/Heat.mkv", b"usb")

    result = plan(bay, backlog=bay.backlog(), baseline={})

    assert result["state"] == "HOLD"
    assert result["conflicts"][0]["reason"] == "DIVERGENT_WITHOUT_BASELINE"


def test_usb_side_update_ingests_when_nas_unchanged(tmp_path):
    bay = make_bay(tmp_path)
    bay.nas("Heat (1995)/Heat.nfo", b"v1")
    bay.usb("Heat (1995)/Heat.nfo", b"v1")
    baseline = bay.baseline()
    bay.usb("Heat (1995)/Heat.nfo", b"v2-edited", mtime_ns=MTIME + 10**12)

    result = plan(bay, backlog=bay.backlog(), baseline=baseline)

    assert result["state"] == "READY"
    assert result["actions"][0]["reason"] == "USB_UPDATED"


def test_vanished_backlog_source_is_notice_and_does_not_block(tmp_path):
    bay = make_bay(tmp_path)
    gone = bay.nas("Heat (1995)/Heat.720p.mkv", b"old")
    backlog = bay.backlog("Heat (1995)/Heat.720p.mkv")
    gone.unlink()
    bay.usb("Elf (2003)/Elf.mkv", b"buddy")

    result = plan(bay, backlog=backlog, baseline={})

    assert result["state"] == "READY"
    assert result["notices"][0]["reason"] == "BACKLOG_SOURCE_GONE"


def test_usb_clutter_is_ignored(tmp_path):
    bay = make_bay(tmp_path)
    baseline = bay.baseline()
    bay.usb("Thumbs.db", b"x")
    bay.usb("._Elf.mkv", b"x")
    bay.usb(".Trash-1000/files/old.mkv", b"x")
    bay.usb("Elf (2003)/.Elf.mkv.loadmaster-partial", b"x")

    result = plan(bay, backlog=bay.backlog(), baseline=baseline)

    assert result["state"] == "CLEAR"


def test_digest_changes_when_source_changes(tmp_path):
    bay = make_bay(tmp_path)
    baseline = bay.baseline()
    path = bay.usb("Elf (2003)/Elf.mkv", b"buddy")

    first = plan(bay, backlog=bay.backlog(), baseline=baseline)
    same = plan(bay, backlog=bay.backlog(), baseline=baseline)
    os.utime(path, ns=(MTIME + 5, MTIME + 5))
    changed = plan(bay, backlog=bay.backlog(), baseline=baseline)

    assert first["digest"] == same["digest"]
    assert first["digest"] != changed["digest"]


def test_ingest_only_plan_produces_ready_preflight(tmp_path):
    bay = make_bay(tmp_path)
    baseline = bay.baseline()
    bay.usb("Elf (2003)/Elf.mkv", b"buddy")
    result = plan(bay, backlog=bay.backlog(), baseline=baseline)

    preflight = physical_preflight(
        plan=result,
        cartridge=bay.cartridge,
        device_serial="2532EA8D3ED1",
        identity_verified=True,
        baseline_verified=True,
        backlog_verified=True,
        generated_at_monotonic=1.0,
    )

    assert preflight.backup_files == 0
    assert preflight.ingest_files == 1
    assert preflight.ready
