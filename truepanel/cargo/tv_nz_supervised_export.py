"""Checkpoint 21: physically supervised, exact-one-file TV N-Z export actuator.

No CLI, GPIO creation or mount authorization. Caller must supply a fresh
host-owned, already-confirmed Copy-button bridge, exact authenticated write
window, and TWO independently checked recovery protections. This function
does NOT support USB->HDD import, arbitrary paths, deletions or overwrites.
"""
from __future__ import annotations

import os
import stat
from pathlib import Path
from typing import Callable

from .backup_executor import BackupExecutionError, attest_cartridge_read_only
from .backup_evidence_commit import commit_verified_backup
from .bidirectional_host_scope import (
    CargoScope, _stat_and_hash, inspect_bidirectional, validate_scope,
)
from .physical_backup_actuator import _writable_identity
from .supervised_bidirectional_batch import transfer_one_approved
from .supervised_mount import SupervisedWriteWindow
from .tv_nz_ro_watchdog import (
    TvNzPin, mount_mode, TV_NZ_LIBRARY, TV_NZ_CARTRIDGE_ROOT,
    TV_NZ_TEST_RELATIVE, TV_NZ_MOUNT, TV_NZ_BY_ID,
    TV_NZ_UUID, TV_NZ_SERIAL,
)
from tools.loadmaster_tv_nz_hdd_export_scope import (
    EXPECTED_BYTES, EXPECTED_SHA256, EXPECTED_FILE, EXPECTED_DEST,
    qualify_read_only,
)

STATE = Path("/mnt/SSDs/Applications/Loadmaster-Watchdog-Qualification")
EVIDENCE = STATE / "tv-nz-production"
MANIFEST = EVIDENCE / "backup-manifest.json"
RSYNC_TIMEOUT_SECONDS = 60


def _root_only(folder: Path) -> None:
    if (not folder.is_absolute() or not folder.is_relative_to(STATE)
            or folder == STATE or folder.is_symlink() or
            not folder.is_dir()):
        raise BackupExecutionError("TV N-Z production evidence directory not qualified")
    meta = folder.stat()
    if meta.st_uid != 0 or meta.st_mode & 0o077 or not stat.S_ISDIR(meta.st_mode):
        raise BackupExecutionError("TV N-Z production evidence must be root-only")


def _exact_scope(scope: CargoScope) -> None:
    validate_scope(scope)
    if (scope.cartridge_id != "tv-n-z"
            or scope.cartridge_uuid != TV_NZ_UUID
            or scope.device_serial != TV_NZ_SERIAL
            or len(scope.actions) != 1
            or scope.actions[0].direction != "NAS_TO_USB"
            or scope.actions[0].relative_path != TV_NZ_TEST_RELATIVE
            or scope.actions[0].size_bytes != EXPECTED_BYTES
            or scope.actions[0].sha256 != EXPECTED_SHA256):
        raise BackupExecutionError("TV N-Z one-episode scope not exact")


def _attest_ro() -> None:
    observed = attest_cartridge_read_only(
        mount=TV_NZ_MOUNT, registered_uuid=TV_NZ_UUID,
        registered_by_id=TV_NZ_BY_ID)
    if (not observed.matches_registry or not observed.read_only
            or mount_mode(TvNzPin()) != "ro"):
        raise BackupExecutionError("TV N-Z cartridge not independently RO")


def _fresh_action(scope: CargoScope, *, allow_existing: bool = False) -> None:
    actual = inspect_bidirectional(
        nas_root=TV_NZ_LIBRARY, usb_root=TV_NZ_CARTRIDGE_ROOT,
        entries=(("NAS_TO_USB", TV_NZ_TEST_RELATIVE),),
        recover_verified=allow_existing)
    if actual != scope.actions:
        raise BackupExecutionError("TV N-Z approved action no longer matches")


def execute_one_export(*, scope: CargoScope, bridge,
                       writable_session: SupervisedWriteWindow,
                       watchdog_verified: Callable[[], bool],
                       rescue_timer_verified: Callable[[], bool],
                       manifest: Path = MANIFEST) -> dict:
    """Consume fresh host GPIO, copy one new file, return USB RO, then receipt.

    Emergency recovery is entirely external to this function. It must be
    started by a trusted host independently before invoking this actuator.
    """
    _exact_scope(scope)
    if (type(writable_session) is not SupervisedWriteWindow
            or writable_session.mount != TV_NZ_MOUNT
            or writable_session.by_id != TV_NZ_BY_ID
            or writable_session.uuid != TV_NZ_UUID
            or not callable(watchdog_verified)
            or not callable(rescue_timer_verified)
            or not isinstance(manifest, Path) or manifest != MANIFEST):
        raise BackupExecutionError("TV N-Z physical host context not trusted")
    _root_only(STATE)
    _root_only(EVIDENCE)
    if not hasattr(bridge, "consume_read_only"):
        raise BackupExecutionError("missing host-owned GPIO bridge")

    # Replan/rehash under RO immediately before burning an approval.
    inspection = qualify_read_only()
    if (inspection["state"] != "TV_NZ_HDD_EXPORT_SCOPE_READ_ONLY_PASS"
            or inspection["source_sha256"] != EXPECTED_SHA256
            or inspection["size_bytes"] != EXPECTED_BYTES
            or inspection["physical_authorized"] is not False):
        raise BackupExecutionError("TV N-Z physical readiness changed")
    _attest_ro()
    _fresh_action(scope)
    if os.path.lexists(EXPECTED_DEST):
        raise BackupExecutionError("no-overwrite destination occupied")
    if not watchdog_verified() or not rescue_timer_verified():
        raise BackupExecutionError("independent guard and rescue timer both required")

    # Session bridge is the only source of genuine physical approval evidence;
    # it burns its approval before a mount may become writable.
    evidence = bridge.consume_read_only()
    if (type(evidence) is not dict
            or evidence.get("state") != "HOST_APPROVAL_EVIDENCE_ONLY"
            or evidence.get("cartridge_id") != scope.cartridge_id
            or evidence.get("plan_digest") != scope.digest
            or evidence.get("executed") is not False
            or evidence.get("physical_execution_enabled") is not False):
        raise BackupExecutionError("physical Copy-button evidence mismatch")

    with writable_session:
        _writable_identity(
            mount=TV_NZ_MOUNT, by_id=TV_NZ_BY_ID, uuid=TV_NZ_UUID)
        if not watchdog_verified() or not rescue_timer_verified():
            raise BackupExecutionError("guard or rescue timer lost inside RW window")
        _fresh_action(scope)
        if os.path.lexists(EXPECTED_DEST):
            raise BackupExecutionError("destination collision after approval")
        copied = transfer_one_approved(
            nas_root=TV_NZ_LIBRARY,
            usb_root=TV_NZ_CARTRIDGE_ROOT,
            action=scope.actions[0],
            device_serial=TV_NZ_SERIAL,
            rsync_timeout_seconds=RSYNC_TIMEOUT_SECONDS)
        if copied.get("state") != "NEW_VERIFIED_COPY":
            raise BackupExecutionError("TV N-Z pilot must publish one new file")
        _writable_identity(
            mount=TV_NZ_MOUNT, by_id=TV_NZ_BY_ID, uuid=TV_NZ_UUID)
        if not watchdog_verified() or not rescue_timer_verified():
            raise BackupExecutionError("guard or timer failed post-transfer")

    # No host-only receipt until the independently authenticated USB is RO.
    _attest_ro()
    if (_stat_and_hash(EXPECTED_FILE) != (EXPECTED_BYTES, EXPECTED_SHA256)
            or _stat_and_hash(EXPECTED_DEST) != (EXPECTED_BYTES, EXPECTED_SHA256)):
        raise BackupExecutionError("read-only final source/destination hash mismatch")
    receipt = commit_verified_backup(
        source=EXPECTED_FILE,
        destination=EXPECTED_DEST, manifest=manifest,
        expected_size=EXPECTED_BYTES, expected_sha256=EXPECTED_SHA256)
    return {
        "state": "TV_NZ_HDD_EXPORT_VERIFIED",
        "new_copy": True,
        "source": str(EXPECTED_FILE),
        "destination": str(EXPECTED_DEST),
        "sha256": EXPECTED_SHA256,
        "bytes_verified": EXPECTED_BYTES,
        "cartridge_read_only": True,
        "receipt_state": receipt["state"],
        "approval_consumed": True,
        "hdd_written": False,
    }
