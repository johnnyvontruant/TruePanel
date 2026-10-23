#!/usr/bin/env python3
"""Production TV N-Z read-only Flight Deck receipt reporter.

Independent proof is checked afresh against BOTH source and USB file plus
SSD-hosted manifest. No GPIO, USB mounts, bulk scanning or physical writes.
Optional --publish-ssd-only atomically publishes one 0600 host-side telemetry
snapshot for Mission Control, NEVER a transfer plan or execution approval.
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

from truepanel.cargo.backup_manifest import validate_backup_manifest
from truepanel.cargo.backup_executor import BackupExecutionError
from truepanel.cargo.bidirectional_host_scope import _stat_and_hash
from truepanel.cargo.flightdeck import KIND, read_flightdeck
from truepanel.cargo.tv_nz_ro_watchdog import (
    TvNzPin, mount_mode, TV_NZ_SERIAL, TV_NZ_UUID,
    TV_NZ_TEST_RELATIVE,
)
from truepanel.cargo.tv_nz_supervised_export import (
    STATE, EVIDENCE, MANIFEST, EXPECTED_FILE, EXPECTED_DEST,
    EXPECTED_BYTES, EXPECTED_SHA256, _root_only,
)

OUTPUT = STATE / "flightdeck-tv-nz-production.json"


def build_verified_copy_snapshot(*, source: Path, destination: Path,
                                 manifest: Path, relative_path: str,
                                 size_bytes: int, sha256: str,
                                 serial: str, uuid: str,
                                 cartridge_label: str) -> dict:
    """Require exact recorded and *currently* checksum-matching media copies.

    This pure read-only evidence verifier is parameterized for synthetic tests;
    only the fixed TV N-Z wrapper below is exposed as a production CLI.
    """
    if (type(size_bytes) is not int or size_bytes <= 0
            or not isinstance(sha256, str) or len(sha256) != 64
            or any(ch not in "0123456789abcdef" for ch in sha256)
            or not isinstance(relative_path, str)
            or relative_path.startswith("/")
            or any(piece in {"", ".", ".."} for piece in relative_path.split("/"))
            or len(relative_path.split("/")) != 2
            or not source.is_absolute() or not destination.is_absolute()
            or not manifest.is_absolute()
            or not isinstance(cartridge_label, str) or not cartridge_label
            or not isinstance(serial, str) or not serial
            or not isinstance(uuid, str) or not uuid):
        raise BackupExecutionError("invalid receipt preview contract")
    if any("daria" in piece.casefold() for piece in relative_path.split("/")):
        raise BackupExecutionError("permanently protected media excluded")
    for path in (source, destination, manifest):
        if path.is_symlink() or any(part.is_symlink() for part in path.parents):
            raise BackupExecutionError("symlink in source/destination/receipt path")

    if (_stat_and_hash(source) != (size_bytes, sha256)
            or _stat_and_hash(destination) != (size_bytes, sha256)):
        raise BackupExecutionError("backup media checksum/size mismatch")

    try:
        receipt = validate_backup_manifest(manifest)
    except (OSError, ValueError) as exc:
        raise BackupExecutionError("production backup receipt invalid") from exc
    proof = [i for i in receipt["items"] if i["path"] == str(source)]
    if (len(proof) != 1 or proof[0].get("size_bytes") != size_bytes
            or proof[0].get("sha256") != sha256):
        raise BackupExecutionError("receipt does not uniquely match verified media")
    stamp = datetime.now(timezone.utc).isoformat()
    return {
        "schema_version": 1, "kind": KIND,
        "generated_at": stamp,
        "mode": "PREVIEW_ONLY", "read_only": True,
        "physical_authorized": False, "transfer_enabled": False,
        "cartridge": {
            "label": cartridge_label, "serial": serial,
            "uuid": uuid, "mount_mode": "ro",
        },
        "summary": {"export": 0, "ingest": 0,
                    "verified": 1, "conflicts": 0},
        "actions": [{
            "direction": "NAS_TO_USB",
            "relative_path": relative_path,
            "size_bytes": size_bytes, "sha256": sha256,
            "status": "VERIFIED",
        }],
        # A completed hash does not prove the watchdog itself was activated;
        # do not misreport a guard recovery without a separately authenticated
        # guard execution receipt.
        "receipts": {"backup": 1, "ingest": 0, "guard": "UNKNOWN"},
    }


def build_current_tv_nz_snapshot() -> dict:
    _root_only(STATE)
    _root_only(EVIDENCE)
    if mount_mode(TvNzPin()) != "ro":
        raise BackupExecutionError("TV N-Z must be authenticated RO")
    report = build_verified_copy_snapshot(
        source=EXPECTED_FILE, destination=EXPECTED_DEST, manifest=MANIFEST,
        relative_path=TV_NZ_TEST_RELATIVE,
        size_bytes=EXPECTED_BYTES, sha256=EXPECTED_SHA256,
        serial=TV_NZ_SERIAL, uuid=TV_NZ_UUID, cartridge_label="TV N-Z")
    if mount_mode(TvNzPin()) != "ro":
        raise BackupExecutionError("TV N-Z mount changed during receipt verification")
    return report


def publish_private_ssd(report: dict, dest: Path = OUTPUT) -> None:
    """Atomic, root-private, fixed-path host telemetry only; never USB writes."""
    if dest != OUTPUT or dest.is_symlink():
        raise BackupExecutionError("untrusted Flight Deck output path")
    _root_only(STATE)
    if any(part.is_symlink() for part in dest.parents):
        raise BackupExecutionError("symlinked telemetry directory")
    temp = None
    try:
        fd, path = tempfile.mkstemp(
            prefix=".tv-nz-flightdeck-", dir=STATE)
        temp = Path(path)
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(report, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, dest)
        temp = None
        folder = os.open(STATE, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(folder)
        finally:
            os.close(folder)
    finally:
        if temp is not None:
            temp.unlink(missing_ok=True)
    if read_flightdeck(dest).get("state") != "READY":
        raise BackupExecutionError("published Flight Deck snapshot invalid")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--publish-ssd-only", action="store_true")
    args = parser.parse_args(argv)
    try:
        snapshot = build_current_tv_nz_snapshot()
        if args.publish_ssd_only:
            publish_private_ssd(snapshot)
        print(json.dumps({
            "state": ("TV_NZ_PRODUCTION_FLIGHTDECK_PUBLISHED"
                      if args.publish_ssd_only else
                      "TV_NZ_PRODUCTION_FLIGHTDECK_READ_ONLY_VERIFIED"),
            "snapshot_path": str(OUTPUT) if args.publish_ssd_only else None,
            "verified_current_files": snapshot["summary"]["verified"],
            "receipt_count": snapshot["receipts"]["backup"],
            "cartridge_mount_mode": snapshot["cartridge"]["mount_mode"],
            "mission_control_config_changed": False,
            "physical_authorized": False, "usb_written": False,
        }, indent=2))
        return 0
    except (BackupExecutionError, ValueError, OSError) as exc:
        print("TV_NZ_PRODUCTION_FLIGHTDECK_HOLD:", str(exc),
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
