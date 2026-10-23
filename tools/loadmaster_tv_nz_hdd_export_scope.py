"""Non-actuating HDD -> TV N-Z physical-export *scope* qualification.

Checkpoint 20: identify exactly one allowed HDD source and authentic cartridge.
This module NEVER mounts, arms Copy-button GPIO, modifies metadata, copies
data, or returns any execution authority. A later runner must independently
re-check this entire contract immediately before a physical write window.
"""
from __future__ import annotations

import json
import os
import re
import stat
from pathlib import Path

from truepanel.cargo.backup_executor import (
    BackupExecutionError, attest_cartridge_read_only,
)
from truepanel.cargo.bidirectional_host_scope import (
    CargoScope, inspect_bidirectional,
)
from truepanel.cargo.cartridges import load_cartridge_registry
from truepanel.cargo.os_housekeeping import ignored_os_path
from truepanel.cargo.tv_nz_ro_watchdog import (
    TV_NZ_MOUNT, TV_NZ_BY_ID, TV_NZ_UUID, TV_NZ_SERIAL,
    TV_NZ_LIBRARY, TV_NZ_CARTRIDGE_ROOT, TV_NZ_TEST_RELATIVE,
    TvNzPin, mount_mode,
)

REGISTRY = Path("/var/lib/truepanel/loadmaster/cartridges.json")
BACKLOG = Path("/var/lib/truepanel/loadmaster/pending-cargo.json")
EXPECTED_BYTES = 336388391
EXPECTED_SHA256 = "c819a0d72cdb18c679824c687559847beb435747bb9f62c252eb906179c554ab"
EXPECTED_FILE = TV_NZ_LIBRARY / TV_NZ_TEST_RELATIVE
EXPECTED_DEST = TV_NZ_CARTRIDGE_ROOT / TV_NZ_TEST_RELATIVE


def _no_links(path: Path) -> None:
    if not path.is_absolute() or ".." in path.parts:
        raise BackupExecutionError("nonabsolute or traversing pilot path")
    for part in (path, *path.parents):
        if part.is_symlink():
            raise BackupExecutionError("symlink in pilot scope")


def _validate_registry(registry: Path) -> None:
    cartridges = [c for c in load_cartridge_registry(registry)
                  if c.cartridge_id == "tv-n-z"]
    if len(cartridges) != 1:
        raise BackupExecutionError("TV N-Z cartridge not uniquely registered")
    c = cartridges[0]
    if (c.uuid != TV_NZ_UUID or c.device_serial != TV_NZ_SERIAL
            or c.source_prefix != TV_NZ_LIBRARY
            or c.usb_relative_path != Path("TV N-Z")
            or c.delete_policy != "never"
            or c.allow_backup or c.allow_ingest):
        raise BackupExecutionError("TV N-Z registration changed or is enabled")


def _validate_ledger(backlog: Path) -> None:
    try:
        payload = json.loads(backlog.read_text(encoding="utf-8"))
        entries = payload["items"]
    except (OSError, KeyError, ValueError, TypeError) as exc:
        raise BackupExecutionError("cannot inspect pending-cargo ledger") from exc
    matches = [i for i in entries if
               isinstance(i, dict) and i.get("current_path") == str(EXPECTED_FILE)]
    if (len(matches) != 1 or type(matches[0].get("size_bytes")) is not int
            or matches[0]["size_bytes"] != EXPECTED_BYTES):
        raise BackupExecutionError("pending pilot ledger item missing or changed")


def qualify_read_only(*, registry: Path = REGISTRY,
                      backlog: Path = BACKLOG) -> dict:
    """Return evidence only, never a physically usable approval or actuator."""
    if ignored_os_path(TV_NZ_TEST_RELATIVE) or any(
            "daria" in part.casefold() for part in EXPECTED_FILE.parts):
        raise BackupExecutionError("protected or housekeeping media not eligible")
    for path in (registry, backlog, TV_NZ_MOUNT, TV_NZ_LIBRARY,
                 TV_NZ_CARTRIDGE_ROOT, EXPECTED_FILE, EXPECTED_DEST):
        _no_links(path)
    if (not TV_NZ_LIBRARY.is_dir() or
            not TV_NZ_CARTRIDGE_ROOT.is_dir() or
            not EXPECTED_FILE.is_file()):
        raise BackupExecutionError("pinned production library/USB root missing")
    info = EXPECTED_FILE.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_size != EXPECTED_BYTES:
        raise BackupExecutionError("pilot source type or size changed")
    if os.path.lexists(EXPECTED_DEST):
        raise BackupExecutionError("pilot destination occupied: no overwrite")
    _validate_registry(registry)
    _validate_ledger(backlog)
    if mount_mode(TvNzPin()) != "ro":
        raise BackupExecutionError("TV N-Z not mounted read-only")
    observed = attest_cartridge_read_only(
        mount=TV_NZ_MOUNT, registered_uuid=TV_NZ_UUID,
        registered_by_id=TV_NZ_BY_ID)
    if not observed.matches_registry or not observed.read_only:
        raise BackupExecutionError("TV N-Z cartridge hardware attestation failed")
    actions = inspect_bidirectional(
        nas_root=TV_NZ_LIBRARY, usb_root=TV_NZ_CARTRIDGE_ROOT,
        entries=(("NAS_TO_USB", TV_NZ_TEST_RELATIVE),))
    if (len(actions) != 1 or actions[0].direction != "NAS_TO_USB"
            or actions[0].relative_path != TV_NZ_TEST_RELATIVE
            or actions[0].size_bytes != EXPECTED_BYTES
            or actions[0].sha256 != EXPECTED_SHA256):
        raise BackupExecutionError("pilot checksum or scope changed")
    free = os.statvfs(TV_NZ_MOUNT)
    available_bytes = free.f_bavail * free.f_frsize
    if available_bytes < EXPECTED_BYTES:
        raise BackupExecutionError("insufficient USB space")
    # A fresh plan fingerprint is informational only; a separate physical
    # session must generate its own nonce and burn GPIO evidence before writes.
    scope = CargoScope("tv-n-z", TV_NZ_UUID, TV_NZ_SERIAL, actions)
    if mount_mode(TvNzPin()) != "ro" or os.path.lexists(EXPECTED_DEST):
        raise BackupExecutionError("mount or destination changed during inspection")
    return {
        "state": "TV_NZ_HDD_EXPORT_SCOPE_READ_ONLY_PASS",
        "source": str(EXPECTED_FILE),
        "destination": str(EXPECTED_DEST),
        "cartridge_id": scope.cartridge_id,
        "uuid": scope.cartridge_uuid,
        "serial": scope.device_serial,
        "direction": "NAS_TO_USB",
        "size_bytes": EXPECTED_BYTES,
        "source_sha256": EXPECTED_SHA256,
        "available_bytes": available_bytes,
        "read_only": True,
        "plan_digest_preview_only": scope.digest,
        "degraded_pool_risk": "ACCEPTED_FOR_PILOT_PLANNING_ONLY",
        "physical_authorized": False,
        "gpio_armed": False,
        "usb_written": False,
        "hdd_written": False,
        "remaining_gates": [
            "QUALIFY_HDD_SOURCE_HOST_ACTUATOR_WITH_EXACT_SCOPE",
            "VERIFY_BOTH_INDEPENDENT_RO_GUARDS_DURING_RW_SESSION",
            "FRESH_PHYSICAL_COPY_BUTTON_CONFIRMATION",
            "HASH_MATCH_AND_COMMIT_RECEIPT_AFTER_VERIFIED_RO",
        ],
    }


if __name__ == "__main__":
    try:
        print(json.dumps(qualify_read_only(), indent=2))
    except (BackupExecutionError, OSError, ValueError) as exc:
        raise SystemExit("TV_NZ_HDD_EXPORT_HOLD: " + str(exc)) from exc
