"""Carry out one approved plan and keep the drive's sync record truthful.

Order: USB removals (frees space) -> copies to USB -> copies to NAS -> NAS
retirements. NAS retirements only run when every copy succeeded, so an old
NAS file is never retired unless its replacement actually arrived.

After the run the drive record holds exactly the files verified identical on
both sides: everything that was already in sync plus everything copied, minus
everything removed. Items that failed keep their previous record entry, so the
next plan reaches the same decision again.
"""

from __future__ import annotations

import os
import threading
import time
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .config import Drive
from .plan import DELETE_USB, RETIRE_NAS, TO_NAS, TO_USB
from .scan import Fingerprint
from .state import DriveRecord, StateStore, write_json_atomic
from .transfer import (
    FATAL_ERRNOS,
    Cancelled,
    ItemError,
    copy_file,
    delete_file,
    retire_file,
    safe_relative,
)

SPACE_MARGIN = 256 * 1024 * 1024
REPLACING_REASONS = frozenset(
    {"UPDATED_ON_NAS", "NEWER_ON_NAS", "UPDATED_ON_USB", "NEWER_ON_USB"}
)
LOG_EACH_ITEM_UP_TO = 300
KEEP_RECEIPTS = 100


@dataclass
class RunContext:
    drive: Drive
    usb_root: Path
    plan: dict[str, Any]
    record: DriveRecord
    store: StateStore
    verify: str = "sha256"
    ingest_owner: tuple[int, int] | None = None
    stop: threading.Event = field(default_factory=threading.Event)
    progress: Callable[[dict[str, Any]], None] | None = None
    source: str = "copy_button"


def _free(path: Path) -> int:
    info = os.statvfs(path)
    return info.f_bavail * info.f_frsize


def execute(ctx: RunContext) -> dict[str, Any]:
    plan = ctx.plan
    drive = ctx.drive
    nas_root = drive.nas_path
    started = time.time()
    stamp = time.strftime("%Y%m%d-%H%M%S", time.localtime(started))
    receipt: dict[str, Any] = {
        "id": f"{stamp}-{drive.key}",
        "drive": drive.name,
        "source": ctx.source,
        "digest": plan["digest"],
        "started": started,
        "state": "RUNNING",
        "reason": None,
        "results": [],
    }

    actions = plan["actions"]
    summary = plan["summary"]
    usb_need = max(0, summary["to_usb_bytes"] - summary["delete_usb_bytes"])
    for root, need in ((ctx.usb_root, usb_need), (nas_root, summary["to_nas_bytes"])):
        if need and _free(root) < need + SPACE_MARGIN:
            receipt.update(state="FAILED", reason=f"not enough free space on {root}")
            return _finish(ctx, receipt, started)

    owner = ctx.ingest_owner
    if owner is None:
        info = nas_root.stat()
        owner = (info.st_uid, info.st_gid)
    if os.geteuid() != 0:
        owner = None

    new_files = dict(ctx.record.files)
    for path, value in plan["in_sync"].items():
        new_files[path] = Fingerprint.from_list(value)
    for path in plan.get("forget", []):
        new_files.pop(path, None)

    total_bytes = summary["to_usb_bytes"] + summary["to_nas_bytes"]
    progress = {
        "total_files": len(actions),
        "done_files": 0,
        "total_bytes": total_bytes,
        "done_bytes": 0,
        "current": None,
    }

    def report() -> None:
        if ctx.progress:
            with suppress(Exception):
                ctx.progress(dict(progress))

    def moved(count: int) -> None:
        progress["done_bytes"] += count
        report()

    fatal: str | None = None
    copy_failed = False
    replaced_root = drive.replaced_dir / stamp

    for raw in actions:
        result = {
            "op": raw["op"],
            "path": raw["path"],
            "size": raw["size"],
            "reason": raw["reason"],
            "outcome": "NOT_ATTEMPTED",
        }
        receipt["results"].append(result)
        if fatal:
            continue
        if raw["op"] == RETIRE_NAS and copy_failed:
            result["outcome"] = "SKIPPED"
            result["error"] = "a copy failed, so the NAS original was kept"
            continue

        progress["current"] = raw["path"]
        report()
        fp = Fingerprint(raw["size"], raw["mtime_ns"])
        try:
            rel = safe_relative(raw["path"])
            if raw["op"] == DELETE_USB:
                delete_file(ctx.usb_root, rel, fp)
                new_files.pop(raw["path"], None)
            elif raw["op"] == RETIRE_NAS:
                retire_file(nas_root, rel, fp, replaced_root)
                new_files.pop(raw["path"], None)
            else:
                to_usb = raw["op"] == TO_USB
                copied = copy_file(
                    source=(nas_root if to_usb else ctx.usb_root) / rel,
                    dest_root=ctx.usb_root if to_usb else nas_root,
                    rel=rel,
                    expected=fp,
                    replace=raw["reason"] in REPLACING_REASONS,
                    stop=ctx.stop,
                    verify=ctx.verify,
                    owner=None if to_usb else owner,
                    before_publish=None
                    if to_usb
                    else (
                        lambda target, rel=rel: _retire_if_present(
                            nas_root, rel, target, replaced_root
                        )
                    ),
                    on_bytes=moved,
                )
                result["sha256"] = copied.sha256
                if copied.resumed_bytes:
                    result["resumed_bytes"] = copied.resumed_bytes
                new_files[raw["path"]] = fp
            result["outcome"] = "DONE"
        except ItemError as error:
            result.update(outcome="FAILED", error=str(error))
            copy_failed = copy_failed or raw["op"] in {TO_USB, TO_NAS}
        except Cancelled:
            result.update(outcome="FAILED", error="cancelled")
            fatal = "cancelled"
        except OSError as error:
            result.update(outcome="FAILED", error=f"{error.strerror or error}")
            copy_failed = copy_failed or raw["op"] in {TO_USB, TO_NAS}
            if error.errno in FATAL_ERRNOS:
                fatal = f"drive error: {error.strerror or error}"
        progress["done_files"] += 1
        report()

    progress["current"] = None
    report()

    ctx.record.files = new_files
    ctx.record.last_sync = time.time()
    ctx.store.save_record(drive.key, ctx.record)

    failed = sum(1 for r in receipt["results"] if r["outcome"] == "FAILED")
    if fatal == "cancelled":
        receipt.update(state="CANCELLED", reason="stopped before finishing")
    elif fatal:
        receipt.update(state="FAILED", reason=fatal)
    elif failed:
        receipt.update(state="PARTIAL", reason=f"{failed} item(s) failed")
    else:
        receipt["state"] = "COMPLETE"
    return _finish(ctx, receipt, started)


def _retire_if_present(nas_root: Path, rel, target: Path, replaced_root: Path) -> None:
    if os.path.lexists(target):
        retire_file(nas_root, rel, None, replaced_root)


def _finish(ctx: RunContext, receipt: dict[str, Any], started: float) -> dict[str, Any]:
    results = receipt["results"]
    done = [r for r in results if r["outcome"] == "DONE"]
    receipt["finished"] = time.time()
    receipt["summary"] = {
        "to_usb_files": sum(1 for r in done if r["op"] == TO_USB),
        "to_nas_files": sum(1 for r in done if r["op"] == TO_NAS),
        "deleted_usb_files": sum(1 for r in done if r["op"] == DELETE_USB),
        "retired_nas_files": sum(1 for r in done if r["op"] == RETIRE_NAS),
        "copied_bytes": sum(r["size"] for r in done if r["op"] in {TO_USB, TO_NAS}),
        "failed_files": sum(1 for r in results if r["outcome"] == "FAILED"),
        "seconds": round(receipt["finished"] - started, 1),
    }

    receipts = ctx.store.root / "receipts"
    with suppress(OSError):
        write_json_atomic(receipts / f"{receipt['id']}.json", receipt)
        old = sorted(receipts.glob("*.json"))[:-KEEP_RECEIPTS]
        for path in old:
            path.unlink()

    store = ctx.store
    if len(done) <= LOG_EACH_ITEM_UP_TO:
        for r in done:
            store.log(
                "moved",
                drive=ctx.drive.name,
                op=r["op"],
                path=r["path"],
                size=r["size"],
                reason=r["reason"],
            )
    store.log(
        "run",
        drive=ctx.drive.name,
        state=receipt["state"],
        reason=receipt["reason"],
        summary=receipt["summary"],
        source=ctx.source,
        receipt=receipt["id"],
    )
    return receipt


__all__ = ["RunContext", "execute"]
