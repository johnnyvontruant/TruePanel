#!/usr/bin/env python3
"""Publish read-only Loadmaster acceptance evidence for Mission Control.

Explicit operator command. Inspects only the fixed synthetic spare lab, then
writes one private SSD telemetry file. No mounts, GPIO reads, rsync or USB writes.
This is a historical verified acceptance snapshot, not a live backup queue.
"""
from __future__ import annotations

import argparse
import json
import os
import stat
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from truepanel.cargo.bidirectional_host_scope import _stat_and_hash
from truepanel.cargo.flightdeck import KIND, read_flightdeck
from tools.loadmaster_spare_bidirectional_preview import (
    SPARE_SERIAL, SPARE_UUID, pinned_spare_identity,
)
from tools.loadmaster_spare_bidirectional_live_fire import (
    ENTRIES, NAS, STATE, USB,
)

OUTPUT = STATE / "flightdeck-acceptance.json"
JOURNAL = STATE / "checkpoint11-acceptance"


def build_snapshot(*, nas: Path, usb: Path, journal: Path,
                   serial: str, uuid: str) -> dict:
    if not journal.is_dir() or journal.is_symlink():
        raise ValueError("missing private acceptance journal")
    recorded = []
    for direction, rel in ENTRIES:
        source_root, destination_root = (nas, usb) if direction == "NAS_TO_USB" else (usb, nas)
        source_size, source_hash = _stat_and_hash(source_root / rel)
        dest_size, dest_hash = _stat_and_hash(destination_root / rel)
        if (source_size, source_hash) != (dest_size, dest_hash):
            raise ValueError("acceptance copy not independently verified")
        recorded.append({
            "direction": direction, "relative_path": rel, "size_bytes": source_size,
            "sha256": source_hash, "status": "VERIFIED"})
    manifest = json.loads((journal / "backup-manifest.json").read_text())
    export = next(a for a in recorded if a["direction"] == "NAS_TO_USB")
    ingest = next(a for a in recorded if a["direction"] == "USB_TO_NAS")
    backup_items = manifest.get("items")
    if (manifest.get("kind") != "truepanel.cargo_backup_manifest"
            or not isinstance(backup_items, list)
            or not any(i.get("path") == str(nas / export["relative_path"])
                       and i.get("sha256") == export["sha256"]
                       and i.get("size_bytes") == export["size_bytes"]
                       for i in backup_items if isinstance(i, dict))):
        raise ValueError("export receipt not verified")
    ingests = []
    guard_verified = False
    for path in sorted(journal.glob("*.json")):
        if path.name == "backup-manifest.json":
            continue
        if path.is_symlink() or len(ingests) > 25:
            raise ValueError("unsafe receipt inventory")
        record = json.loads(path.read_text())
        if record.get("kind") == "truepanel.loadmaster.ingest_verified.v1":
            ingests.append(record)
        if record.get("state") == "RESTORED_RO":
            guard_verified = True
    if not any(r.get("direction") == "USB_TO_NAS"
               and r.get("device_serial") == serial
               and r.get("cartridge_uuid") == uuid
               and r.get("relative_path") == ingest["relative_path"]
               and r.get("sha256") == ingest["sha256"]
               and r.get("size_bytes") == ingest["size_bytes"]
               for r in ingests):
        raise ValueError("ingest receipt not verified")
    if not guard_verified or not list(journal.glob("*.consumed")):
        raise ValueError("missing consumed approval or guard evidence")
    return {
        "schema_version": 1, "kind": KIND,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": "PREVIEW_ONLY", "read_only": True,
        "physical_authorized": False, "transfer_enabled": False,
        "cartridge": {"label": "Spare exFAT Acceptance",
                      "serial": serial, "uuid": uuid, "mount_mode": "ro"},
        "summary": {"export": 0, "ingest": 0,
                    "verified": len(recorded), "conflicts": 0},
        "actions": recorded,
        "receipts": {"backup": 1, "ingest": 1, "guard": "RESTORED_RO"},
    }


def _publish_private(report: dict, dest: Path) -> None:
    if dest != OUTPUT or dest.is_symlink() or STATE.is_symlink():
        raise ValueError("snapshot may only be published to fixed SSD state path")
    meta = STATE.stat()
    if not stat.S_ISDIR(meta.st_mode) or meta.st_uid != 0 or meta.st_mode & 0o077:
        raise ValueError("private root-owned 0700 state directory required")
    fd, tmp = tempfile.mkstemp(prefix=".flightdeck-", dir=STATE)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w") as stream:
            json.dump(report, stream, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, dest)
        dfd = os.open(STATE, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(dfd)
        finally:
            os.close(dfd)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    if read_flightdeck(dest).get("state") != "READY":
        raise ValueError("published snapshot did not validate")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--publish-ssd-only", action="store_true")
    args = parser.parse_args(argv)
    try:
        if pinned_spare_identity() != (SPARE_UUID, SPARE_SERIAL, True):
            raise ValueError("spare identity or RO mount failed")
        result = build_snapshot(nas=NAS, usb=USB, journal=JOURNAL,
                                serial=SPARE_SERIAL, uuid=SPARE_UUID)
        if args.publish_ssd_only:
            _publish_private(result, OUTPUT)
        print(json.dumps({
            "state": "LOADMASTER_FLIGHTDECK_PUBLISHED" if args.publish_ssd_only
                     else "READ_ONLY_FLIGHTDECK_PREVIEW",
            "usb_written": False, "gpio_armed": False,
            "snapshot_path": str(OUTPUT) if args.publish_ssd_only else None,
            "summary": result["summary"], "receipts": result["receipts"],
            "cartridge": result["cartridge"],
        }, indent=2))
        return 0
    except (OSError, ValueError, RuntimeError, KeyError) as error:
        print("FLIGHTDECK_HOLD:", str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
