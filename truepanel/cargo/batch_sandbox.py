"""Sandbox-only three-file Loadmaster orchestration.

This cannot mount media, consume a Copy press, or authorize physical USB
writes. It exercises the production-quality one-file copy primitive and
verified evidence writer against disposable roots.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Sequence

from .backup_evidence_commit import commit_verified_backup
from .backup_executor import BackupExecutionError
from .backup_transaction import _safe_parts, transfer_one_file


def _sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            h.update(chunk)
    return h.hexdigest()


def execute_sandbox_batch(*, sandbox_root: Path, nas: Path, usb: Path,
                          manifest: Path, names: Sequence[str],
                          interrupt_after: int | None = None) -> dict:
    """Verify each of 1-3 entries, recording evidence independently.

    An interruption after a published file is recoverable by hashing
    that destination on retry, never by replacing it.
    """
    if not 1 <= len(names) <= 3 or len(set(names)) != len(names):
        raise BackupExecutionError("batch needs 1 to 3 unique files")
    if any(not isinstance(name, str) for name in names):
        raise BackupExecutionError("invalid batch item")
    if (not sandbox_root.is_absolute() or sandbox_root.is_symlink()
            or not sandbox_root.is_dir() or manifest.parent != sandbox_root
            or manifest.is_symlink()):
        raise BackupExecutionError("manifest outside disposable sandbox")
    root = sandbox_root.resolve(strict=True)
    for directory in (nas, usb):
        if (not directory.is_absolute() or directory.is_symlink()
                or not directory.is_dir()
                or directory.resolve(strict=True).parent != root
                or os.path.ismount(directory)
                or directory.stat().st_dev != root.stat().st_dev):
            raise BackupExecutionError("batch roots outside sandbox")

    candidates = []
    for name in names:
        folder, filename = _safe_parts(name)
        source = nas / folder / filename
        destination = usb / folder / filename
        if source.is_symlink() or source.parent.is_symlink() or not source.is_file():
            raise BackupExecutionError("unsafe or missing source")
        if destination.is_symlink() or destination.parent.is_symlink():
            raise BackupExecutionError("unsafe destination")
        size = source.stat().st_size
        digest = _sha(source)
        if destination.exists():
            if not destination.is_file() or destination.stat().st_size != size or _sha(destination) != digest:
                raise BackupExecutionError("existing destination mismatch")
        candidates.append((name, source, destination, size, digest))

    finished = []
    for name, source, destination, size, digest in candidates:
        if destination.exists():
            state = "RECOVERED_VERIFIED_COPY"
        else:
            result = transfer_one_file(
                source_root=nas, usb_root=usb, relative_path=name,
                expected_size=size, sandbox_root=sandbox_root)
            if result["sha256"] != digest:
                raise BackupExecutionError("source changed since batch inspection")
            state = "NEW_VERIFIED_COPY"
        evidence = commit_verified_backup(
            source=source, destination=destination, manifest=manifest,
            expected_size=size, expected_sha256=digest)
        finished.append({"relative_path": name, "copy_state": state,
                         "manifest_state": evidence["state"]})
        if interrupt_after is not None and len(finished) == interrupt_after:
            raise InterruptedError("injected interruption after verified manifest")
    return {"state": "SANDBOX_BATCH_VERIFIED", "files": finished,
            "physical_authorized": False, "physical_copy": False}
