"""Stage-only, host-gated bounded batch actuator.

Not wired to production, has no CLI and cannot arm its own GPIO. The caller
must own the one-use physical callback, cartridge attestation, and mount.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Callable

from .backup_executor import BackupExecutionError
from .batch_authorization import BatchApprovalScope, BatchItem
from .backup_evidence_commit import commit_verified_backup
from .backup_transaction import _copy_validated_roots, _safe_parts
from .physical_backup_actuator import _writable_identity


def execute_host_batch_core(*, scope: BatchApprovalScope, bridge,
                            reattest: Callable[[], tuple[BatchItem, ...]],
                            nas: Path, usb: Path, mount: Path, by_id: str,
                            uuid: str, manifest: Path, writable_session) -> dict:
    """Consume approval once, then verify/copy each scoped file separately.

    Reattestation occurs before consumption and again before every file. A
    failure ends execution. Recovery is a separate read-only workflow; it
    must not resume unfinished copies using this already-spent authority.
    """
    if (not all(isinstance(p, Path) and p.is_absolute()
                for p in (nas, usb, mount, manifest))
            or any(p.is_symlink() for p in (nas, usb, mount, manifest))
            or scope.cartridge_uuid != uuid or writable_session is None):
        raise BackupExecutionError('unsafe host batch context')
    if not callable(reattest):
        raise BackupExecutionError('missing batch reattestation')
    initial = reattest()
    if type(initial) is not tuple or initial != scope.items:
        raise BackupExecutionError('batch changed before authorization')
    # Only this host-owned bridge may consume the physical callback. The
    # approval evidence is already burned by its durable host journal.
    evidence = bridge.consume_read_only()
    scope.consume(host_evidence=evidence, fresh_digest=scope.digest)
    completed = []
    with writable_session:
        _writable_identity(mount=mount, by_id=by_id, uuid=uuid)
        for item in scope.items:
            if reattest() != scope.items:
                raise BackupExecutionError('batch changed during execution')
            _writable_identity(mount=mount, by_id=by_id, uuid=uuid)
            folder, filename = _safe_parts(item.relative_path)
            source = nas / folder / filename
            dest = usb / folder / filename
            if not source.is_file() or source.is_symlink() or dest.is_symlink():
                raise BackupExecutionError('unsafe batch source or destination')
            if os.path.lexists(dest):
                # Never overwrite, even if bytes appear correct. Reconcile
                # published files in a separate RO recovery operation.
                raise BackupExecutionError('destination occupied; recovery required')
            result = _copy_validated_roots(
                source_root=nas, usb_root=usb,
                relative_path=item.relative_path, expected_size=item.size_bytes)
            if result['sha256'] != item.sha256:
                raise BackupExecutionError('copied file differs from batch scope')
            commit_verified_backup(
                source=source, destination=dest, manifest=manifest,
                expected_size=item.size_bytes, expected_sha256=item.sha256)
            completed.append(item.relative_path)
    return {'state': 'HOST_BATCH_VERIFIED', 'completed': completed,
            'authorization_consumed': True}
