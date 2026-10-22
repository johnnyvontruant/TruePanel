"""End-to-end disposable SANDBOX acceptance only. Never grants USB authority."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Any

from .backup_coordinator import _action, canonical_plan_digest, execute_sandbox_plan
from .backup_evidence_commit import commit_verified_backup
from .backup_executor import BackupExecutionError
from .backup_transaction import _safe_parts


def run_sandbox_acceptance(*, plan: dict[str, Any], sandbox_root: Path,
                           fault: str | None = None) -> dict[str, Any]:
    """Copy + evidence merge, or recover a verified published copy after interruption.

    The manifest is local to the disposable sandbox. Neither hardware, GPIO,
    nor an existing real Loadmaster manifest is reachable via this interface.
    """
    if fault not in (None, 'after_publish'):
        raise BackupExecutionError('unsupported acceptance fault')
    if (not sandbox_root.is_absolute() or sandbox_root.is_symlink() or
            not sandbox_root.is_dir() or os.path.ismount(sandbox_root)):
        raise BackupExecutionError('sandbox required')
    root = sandbox_root.resolve(strict=True)
    # Require explicit disposable test workspace; never an arbitrary library path.
    if not any(root.is_relative_to(Path(base).resolve()) and root != Path(base).resolve()
               for base in ('/tmp', '/var/tmp')):
        raise BackupExecutionError('sandbox must reside under temporary storage')
    marker = root / '.loadmaster-disposable-sandbox'
    if marker.is_symlink() or not marker.is_file() or marker.read_text().strip() != 'TEST-ONLY':
        raise BackupExecutionError('disposable sandbox marker required')
    nas = Path(plan.get('nas_root', ''))
    usb = Path(plan.get('usb_root', ''))
    if (nas != root / 'nas' or usb != root / 'usb' or
            any(p.is_symlink() or not p.is_dir() or os.path.ismount(p) or
                p.resolve(strict=True).parent != root or
                p.stat().st_dev != root.stat().st_dev for p in (nas, usb))):
        raise BackupExecutionError('only disposable sandbox roots accepted')
    action = _action(plan)
    folder, filename = _safe_parts(action['relative_path'])
    source = nas / folder / filename
    destination = usb / folder / filename
    manifest = root / 'manifest.json'
    if manifest.is_symlink():
        raise BackupExecutionError('manifest symlink refused')
    digest = canonical_plan_digest(plan)
    # Existing destination: only permit evidence recovery after independently
    # hashing both immutable-looking copies and matching their size.
    if destination.exists() or destination.is_symlink():
        if destination.is_symlink() or (usb / folder).is_symlink():
            raise BackupExecutionError('destination symlink refused')
        if not source.is_file() or not destination.is_file():
            raise BackupExecutionError('invalid recovery file')
        copy_state = 'RECOVERED_PUBLISHED_COPY'
    else:
        execute_sandbox_plan(plan=plan, sandbox_root=root)
        copy_state = 'NEW_SANDBOX_COPY'
    if not source.is_file() or source.is_symlink():
        raise BackupExecutionError('source not regular')
    # The evidence committer independently hashes source and destination again.
    checksum = hashlib.sha256()
    with source.open('rb') as stream:
        while chunk := stream.read(1024 * 1024):
            checksum.update(chunk)
    expected = checksum.hexdigest()
    if source.stat().st_size != action['size_bytes']:
        raise BackupExecutionError('source changed from plan')
    if fault == 'after_publish':
        raise BackupExecutionError('INJECTED_AFTER_PUBLISH_BEFORE_EVIDENCE')
    result = commit_verified_backup(source=source, destination=destination,
                                    manifest=manifest, expected_size=action['size_bytes'],
                                    expected_sha256=expected)
    return {'state': 'SANDBOX_EVIDENCE_VERIFIED', 'copy_state': copy_state,
            'manifest_state': result['state'], 'plan_digest': digest,
            'physical_transfer': False, 'backup_authorized': False,
            'sandbox_manifest': str(manifest)}
