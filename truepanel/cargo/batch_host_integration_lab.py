"""Stage-only test coordinator for simulated host callback and batch actuator.

Cannot be called against real disks: sandbox roots must be immediate children
of a disposable root, on the same unmounted filesystem.
"""
from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

from .backup_executor import BackupExecutionError
from .batch_host_actuator import execute_host_batch_core


class NoMountWindow:
    """No physical remounts, for disposable sandbox integration only."""
    def __enter__(self):
        return self
    def __exit__(self, typ, value, tb):
        return False


def run_simulated_host_batch(*, sandbox: Path, nas: Path, usb: Path,
                             manifest: Path, scope, bridge, reattest):
    if (not sandbox.is_absolute() or not sandbox.is_dir()
            or sandbox.is_symlink() or manifest.parent != sandbox
            or manifest.is_symlink()):
        raise BackupExecutionError('invalid simulated host sandbox')
    root = sandbox.resolve(strict=True)
    for candidate in (nas, usb):
        if (not candidate.is_absolute() or not candidate.is_dir()
                or candidate.is_symlink() or os.path.ismount(candidate)
                or candidate.resolve(strict=True).parent != root
                or candidate.stat().st_dev != root.stat().st_dev):
            raise BackupExecutionError('simulated host roots outside sandbox')
    # A mock is permitted ONLY in this sandbox-limited integration harness.
    # The actual batch actuator still calls the real descriptor-pinned copier.
    with patch('truepanel.cargo.batch_host_actuator._writable_identity'):
        return execute_host_batch_core(
            scope=scope, bridge=bridge, reattest=reattest, nas=nas, usb=usb,
            mount=usb, by_id='/dev/disk/by-id/sandbox-only',
            uuid=scope.cartridge_uuid, manifest=manifest,
            writable_session=NoMountWindow())
