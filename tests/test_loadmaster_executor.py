from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest
from loadmaster_fixtures import MTIME, make_bay

from truepanel.cargo import executor as executor_module
from truepanel.cargo.backlog import reconcile_backlog
from truepanel.cargo.backup_manifest import validate_backup_manifest
from truepanel.cargo.executor import ExecutorSettings, RunContext, execute_run
from truepanel.cargo.loadmaster import load_inventory
from truepanel.cargo.run_plan import build_run_plan

NOW = datetime(2026, 10, 22, 12, 0, tzinfo=UTC)


def stage(tmp_path):
    bay = make_bay(tmp_path)
    bay.nas("Heat (1995)/Heat.mkv", b"heat")
    bay.usb("Heat (1995)/Heat.mkv", b"heat")
    baseline = bay.baseline()
    bay.nas("Inception (2010)/Inception.mkv", b"dream" * 1000)
    bay.usb("Elf (2003)/Elf.mkv", b"buddy" * 1000)
    backlog = bay.backlog("Inception (2010)/Inception.mkv")
    state = tmp_path / "state"
    state.mkdir()
    return bay, baseline, backlog, state


def context(bay, baseline, backlog, state, *, digest=None, **overrides):
    if digest is None:
        digest = build_run_plan(
            cartridge=bay.cartridge,
            cartridges=[bay.cartridge],
            usb_mount=bay.usb_mount,
            backlog=backlog,
            inventory=baseline,
            ingest_enabled=True,
        )["digest"]
    payload = dict(
        cartridge=bay.cartridge,
        cartridges=[bay.cartridge],
        usb_mount=bay.usb_mount,
        backlog=backlog,
        inventory=baseline,
        inventory_path=state / "movies-e-i.json",
        expected_digest=digest,
        ingest_enabled=True,
        receipts_dir=state / "receipts",
        manifest_path=state / "backup-manifest.json",
        settings=ExecutorSettings(free_space_margin_bytes=0),
        clock=lambda: NOW,
    )
    payload.update(overrides)
    return RunContext(**payload)


def test_confirmed_run_copies_both_directions_and_records_evidence(tmp_path):
    bay, baseline, backlog, state = stage(tmp_path)

    receipt = execute_run(context(bay, baseline, backlog, state))

    assert receipt["state"] == "COMPLETE"
    assert receipt["summary"]["copied_files"] == 2

    backed_up = bay.usb_root / "Inception (2010)/Inception.mkv"
    ingested = bay.nas_root / "Elf (2003)/Elf.mkv"
    assert backed_up.read_bytes() == b"dream" * 1000
    assert ingested.read_bytes() == b"buddy" * 1000
    assert backed_up.stat().st_mtime_ns == MTIME
    assert ingested.stat().st_mtime_ns == MTIME

    # The receipt is the durable transfer log.
    saved = json.loads((state / "receipts" / f"{receipt['run_id']}.json").read_text())
    assert saved["state"] == "COMPLETE"
    assert {r["outcome"] for r in saved["results"]} == {"COPIED"}

    # Backup evidence clears the durable backlog on the next reconcile.
    manifest = validate_backup_manifest(state / "backup-manifest.json")
    assert [item["path"] for item in manifest["items"]] == [
        str(bay.nas_root / "Inception (2010)/Inception.mkv")
    ]
    remaining, report = reconcile_backlog(
        previous=backlog, cargo_items=[], manifest=manifest, observed_at=NOW
    )
    assert remaining["items"] == []
    assert report["verified"] == 1

    # Inventory baseline now includes both moved files.
    inventory = load_inventory(state / "movies-e-i.json", cartridge_id="movies-e-i")
    assert set(inventory) == {
        "Heat (1995)/Heat.mkv",
        "Inception (2010)/Inception.mkv",
        "Elf (2003)/Elf.mkv",
    }

    # A second plan is now clear: nothing moves twice.
    again = build_run_plan(
        cartridge=bay.cartridge,
        cartridges=[bay.cartridge],
        usb_mount=bay.usb_mount,
        backlog=remaining,
        inventory=inventory,
        ingest_enabled=True,
    )
    assert again["state"] == "CLEAR"


def test_changed_plan_aborts_without_writes(tmp_path):
    bay, baseline, backlog, state = stage(tmp_path)
    ctx = context(bay, baseline, backlog, state)
    bay.usb("Gladiator (2000)/Gladiator.mkv", b"arena")  # arrives after the press

    receipt = execute_run(ctx)

    assert receipt["state"] == "FAILED"
    assert "plan changed" in receipt["reason"]
    assert not (bay.usb_root / "Inception (2010)").exists()
    assert not (bay.nas_root / "Elf (2003)").exists()
    assert not (state / "backup-manifest.json").exists()


def test_destination_that_appears_is_never_clobbered(tmp_path, monkeypatch):
    bay, baseline, backlog, state = stage(tmp_path)
    ctx = context(bay, baseline, backlog, state)
    real_copy = executor_module.copy_verified
    intruder = bay.usb_root / "Inception (2010)/Inception.mkv"

    def racing_copy(**kwargs):
        if kwargs["relative"].name == "Inception.mkv":
            intruder.parent.mkdir(parents=True, exist_ok=True)
            intruder.write_bytes(b"someone else's file")
        return real_copy(**kwargs)

    monkeypatch.setattr(executor_module, "copy_verified", racing_copy)

    receipt = execute_run(ctx)

    assert receipt["state"] == "PARTIAL"
    failed = [r for r in receipt["results"] if r["outcome"] == "FAILED"]
    assert failed[0]["error"].startswith("DESTINATION_APPEARED")
    assert intruder.read_bytes() == b"someone else's file"
    assert not list(intruder.parent.glob("*.loadmaster-partial"))


def test_readback_mismatch_fails_item_and_leaves_no_file(tmp_path, monkeypatch):
    bay, baseline, backlog, state = stage(tmp_path)
    ctx = context(bay, baseline, backlog, state)
    monkeypatch.setattr(
        executor_module, "_hash_fd", lambda fd, chunk, stop: ("0" * 64, 0)
    )

    receipt = execute_run(ctx)

    assert receipt["state"] == "PARTIAL"
    assert all(
        r["error"].startswith("VERIFY_HASH_MISMATCH") for r in receipt["results"]
    )
    assert not (bay.usb_root / "Inception (2010)/Inception.mkv").exists()
    assert not (bay.nas_root / "Elf (2003)/Elf.mkv").exists()
    assert not (state / "backup-manifest.json").exists()


def test_insufficient_space_fails_before_any_copy(tmp_path, monkeypatch):
    bay, baseline, backlog, state = stage(tmp_path)
    ctx = context(bay, baseline, backlog, state)
    monkeypatch.setattr(executor_module, "_free_bytes", lambda path: 10)

    receipt = execute_run(ctx)

    assert receipt["state"] == "FAILED"
    assert "insufficient free space" in receipt["reason"]
    assert receipt["results"] == []


def test_fatal_device_error_stops_remaining_files(tmp_path, monkeypatch):
    bay, baseline, backlog, state = stage(tmp_path)
    ctx = context(bay, baseline, backlog, state)

    def device_gone(**kwargs):
        raise OSError(5, "Input/output error")

    monkeypatch.setattr(executor_module, "copy_verified", device_gone)

    receipt = execute_run(ctx)

    assert receipt["state"] == "FAILED"
    outcomes = [r["outcome"] for r in receipt["results"]]
    assert outcomes == ["FAILED", "NOT_ATTEMPTED"]


def test_existing_manifest_evidence_is_preserved(tmp_path):
    bay, baseline, backlog, state = stage(tmp_path)
    (state / "backup-manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "kind": "truepanel.cargo_backup_manifest",
                "created_at": "2026-10-01T00:00:00+00:00",
                "source": "operator",
                "items": [
                    {
                        "path": "/mnt/HDDs/Movies/Other.mkv",
                        "size_bytes": 1,
                        "backed_up_at": "2026-10-01T00:00:00+00:00",
                    }
                ],
            }
        )
    )

    execute_run(context(bay, baseline, backlog, state))

    manifest = validate_backup_manifest(state / "backup-manifest.json")
    assert manifest["source"] == "operator"
    assert len(manifest["items"]) == 2


def test_settings_reject_unknown_verify_mode():
    with pytest.raises(ValueError):
        ExecutorSettings(verify="trust-me")


# ---------------------------------------------------------------- resume


def _copy(bay, source, relative, stop, **kwargs):
    from pathlib import PurePosixPath

    info = source.stat()
    return executor_module.copy_verified(
        source=source,
        destination_root=bay.usb_root,
        relative=PurePosixPath(relative),
        expected_size=info.st_size,
        expected_mtime_ns=info.st_mtime_ns,
        allow_replace=False,
        settings=ExecutorSettings(chunk_bytes=1024 * 1024),
        stop=stop,
        **kwargs,
    )


def test_interrupted_copy_resumes_from_verified_partial(tmp_path):
    import os
    import threading

    bay = make_bay(tmp_path)
    data = os.urandom(6 * 1024 * 1024)
    source = bay.nas("Dune (2021)/Dune.mkv", data)
    stop = threading.Event()
    seen = {"bytes": 0}

    def unplug_after_two_mib(count):
        seen["bytes"] += count
        if seen["bytes"] >= 2 * 1024 * 1024:
            stop.set()

    with pytest.raises(executor_module._Cancelled):
        _copy(bay, source, "Dune (2021)/Dune.mkv", stop, on_bytes=unplug_after_two_mib)

    destination = bay.usb_root / "Dune (2021)/Dune.mkv"
    partials = list(destination.parent.glob("*.loadmaster-partial"))
    assert not destination.exists()
    assert len(partials) == 1
    kept = partials[0].stat().st_size
    assert kept >= 2 * 1024 * 1024

    result = _copy(bay, source, "Dune (2021)/Dune.mkv", threading.Event())

    assert result.resumed_bytes == kept
    assert destination.read_bytes() == data
    assert not list(destination.parent.glob("*.loadmaster-partial"))


def test_corrupt_partial_is_discarded_and_copy_restarts(tmp_path):
    import os
    import threading
    from pathlib import PurePosixPath

    bay = make_bay(tmp_path)
    data = os.urandom(3 * 1024 * 1024)
    source = bay.nas("Dune (2021)/Dune.mkv", data)
    parent = bay.usb_root / "Dune (2021)"
    parent.mkdir(parents=True)
    info = source.stat()
    partial = executor_module.partial_path_for(
        parent,
        PurePosixPath("Dune (2021)/Dune.mkv"),
        expected_size=info.st_size,
        expected_mtime_ns=info.st_mtime_ns,
    )
    partial.write_bytes(b"\0" * 4096)  # same name, wrong bytes

    result = _copy(bay, source, "Dune (2021)/Dune.mkv", threading.Event())

    assert result.resumed_bytes == 0
    assert (parent / "Dune.mkv").read_bytes() == data


def test_partial_from_older_source_version_is_never_reused(tmp_path):
    import os
    import threading

    bay = make_bay(tmp_path)
    source = bay.nas("Dune (2021)/Dune.mkv", os.urandom(1024 * 1024))
    parent = bay.usb_root / "Dune (2021)"
    parent.mkdir(parents=True)
    stale = parent / ".Dune.mkv.0123456789ab.loadmaster-partial"
    stale.write_bytes(source.read_bytes()[:4096])

    result = _copy(bay, source, "Dune (2021)/Dune.mkv", threading.Event())

    assert result.resumed_bytes == 0
    assert not stale.exists()


def test_last_instant_collision_is_never_clobbered(tmp_path, monkeypatch):
    import os
    import threading

    bay = make_bay(tmp_path)
    source = bay.nas("Dune (2021)/Dune.mkv", os.urandom(1024 * 1024))
    destination = bay.usb_root / "Dune (2021)/Dune.mkv"

    def intruder_during_verify(fd):
        if not destination.exists():
            destination.write_bytes(b"another writer")

    monkeypatch.setattr(executor_module, "_drop_cache", intruder_during_verify)

    with pytest.raises(executor_module._ItemError, match="DESTINATION_APPEARED"):
        _copy(bay, source, "Dune (2021)/Dune.mkv", threading.Event())

    assert destination.read_bytes() == b"another writer"


def test_receipt_records_atomic_publish(tmp_path):
    bay, baseline, backlog, state = stage(tmp_path)

    receipt = execute_run(context(bay, baseline, backlog, state))

    assert {r["publish"] for r in receipt["results"]} == {"renameat2_noreplace"}
    assert {r["resumed_bytes"] for r in receipt["results"]} == {0}
