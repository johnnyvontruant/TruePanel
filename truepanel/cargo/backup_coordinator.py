"""Fail-closed one-episode transfer coordinator: PLAN and SANDBOX ONLY.

Does not mount filesystems, consume physical Copy-button confirmations,
write a shared manifest, or perform USB transfers. The physical authorization
entrypoint deliberately fails closed until host-owned integration is validated.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .backup_executor import BackupExecutionError
from .backup_transaction import transfer_one_file, verified_manifest_item


def _action(plan: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(plan, dict) or plan.get('schema_version') != 1:
        raise BackupExecutionError('invalid plan')
    if (plan.get('read_only') is not True or plan.get('state') != 'READY'
            or plan.get('scope') != 'durable_backlog'
            or plan.get('delete_policy') != 'never'
            or plan.get('conflicts') != []):
        raise BackupExecutionError('plan not safely READY')
    actions = plan.get('actions')
    if not isinstance(actions, list) or len(actions) != 1:
        raise BackupExecutionError('plan must contain exactly one action')
    a = actions[0]
    if not isinstance(a, dict) or a.get('direction') != 'NAS_TO_USB':
        raise BackupExecutionError('invalid transfer direction')
    if not isinstance(a.get('relative_path'), str) or type(a.get('size_bytes')) is not int:
        raise BackupExecutionError('invalid transfer action')
    summary = plan.get('summary')
    if (not isinstance(summary, dict) or summary.get('scoped_items') != 1
            or summary.get('backup_files') != 1
            or summary.get('backup_bytes') != a['size_bytes']
            or summary.get('conflicts') != 0 or summary.get('ingest_files') != 0):
        raise BackupExecutionError('plan summary mismatch')
    return a


def canonical_plan_digest(plan: dict[str, Any]) -> str:
    """Canonical digest of the complete immutable transfer intent."""
    _action(plan)
    encoded = json.dumps(plan, sort_keys=True, separators=(',', ':'),
                         ensure_ascii=True, allow_nan=False).encode('ascii')
    return hashlib.sha256(encoded).hexdigest()


def plan_summary(plan: dict[str, Any]) -> dict[str, Any]:
    """Non-actuating operator preview; never authorizes physical transfers."""
    a = _action(plan)
    return {'state': 'PLAN_ONLY', 'digest': canonical_plan_digest(plan),
            'cartridge': plan.get('cartridge', {}).get('id'),
            'relative_path': a['relative_path'], 'size_bytes': a['size_bytes'],
            'executed': False, 'backup_authorized': False}


def execute_sandbox_plan(*, plan: dict[str, Any], sandbox_root: Path,
                         fault: str | None = None) -> dict[str, Any]:
    """Only test roots strictly under the same disposable sandbox are accepted.

    This intentionally delegates the descriptor-relative copy to the
    sandbox-guarded transfer primitive and does not update shared evidence.
    """
    a = _action(plan)
    nas = plan.get('nas_root')
    usb = plan.get('usb_root')
    if not isinstance(nas, str) or not isinstance(usb, str):
        raise BackupExecutionError('invalid plan roots')
    result = transfer_one_file(
        source_root=Path(nas), usb_root=Path(usb),
        relative_path=a['relative_path'], expected_size=a['size_bytes'],
        sandbox_root=sandbox_root, fault=fault,
    )
    evidence = verified_manifest_item(result)
    return {'state': 'VERIFIED_SANDBOX_PLAN', 'plan_digest': canonical_plan_digest(plan),
            'transfer': result, 'evidence_preview': evidence,
            'shared_manifest_updated': False, 'physical_transfer': False}


def execute_physical_plan(*args: Any, **kwargs: Any) -> None:
    """Mandatory hard stop: trusted host transaction is not wired yet."""
    raise BackupExecutionError(
        'PHYSICAL_EXECUTION_DISABLED: no host-owned mount, trusted GPIO handoff, '
        'or atomic shared manifest integration'
    )
