"""Read-only one-episode physical transfer readiness, not execution authority.

The returned READY_FOR_HOST_INTEGRATION state never authorizes a USB write.
This probe intentionally cannot remount, copy, consume GPIO, or commit evidence.
"""
from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .backup_coordinator import canonical_plan_digest, plan_summary
from .backup_executor import attest_cartridge_read_only, BackupExecutionError
from .cartridges import load_cartridge_registry
from .loadmaster import build_backlog_backup_plan


def probe_one_episode(*, registry: Path, backlog: Path, cartridge_id: str,
                      mount: Path, by_id: str, source_path: Path) -> dict[str, Any]:
    """Fail closed using actual registry, backlog and mounted media; no writes."""
    if not source_path.is_absolute() or not mount.is_absolute():
        raise BackupExecutionError('absolute paths required')
    cartridges = [c for c in load_cartridge_registry(registry)
                  if c.cartridge_id == cartridge_id]
    if len(cartridges) != 1:
        raise BackupExecutionError('cartridge not uniquely registered')
    c = cartridges[0]
    if c.allow_ingest or c.delete_policy != 'never':
        raise BackupExecutionError('cartridge safety policy mismatch')
    if c.allow_backup:
        raise BackupExecutionError('backup permission must remain disabled during probe')
    if not c.device_serial:
        # Hardware by-id was validated, but registered serial is still required
        # for the existing Copy-button preflight contract.
        identity_ready = False
    else:
        identity_ready = True
    attestation = attest_cartridge_read_only(
        mount=mount, registered_uuid=c.uuid, registered_by_id=by_id)
    if not attestation.matches_registry or not attestation.read_only:
        raise BackupExecutionError('hardware attestation did not pass')
    ledger = json.loads(backlog.read_text())
    items = [i for i in ledger['items'] if i.get('current_path') == str(source_path)]
    if len(items) != 1:
        raise BackupExecutionError('backlog entry not unique')
    plan = build_backlog_backup_plan(cartridge=c, usb_mount=mount, backlog_items=items)
    summary = plan_summary(plan)
    if summary['state'] != 'PLAN_ONLY' or plan['state'] != 'READY':
        raise BackupExecutionError('single-episode plan not ready')
    action = plan['actions'][0]
    if action['direction'] != 'NAS_TO_USB' or action['size_bytes'] != items[0]['size_bytes']:
        raise BackupExecutionError('plan action mismatch')
    return {
        'state': 'READ_ONLY_PREPARED', 'cartridge_id': cartridge_id,
        'uuid': attestation.uuid, 'filesystem': attestation.filesystem,
        'mount_read_only': True, 'device_serial_registered': identity_ready,
        'plan_digest': canonical_plan_digest(plan), 'source': str(source_path),
        'relative_path': action['relative_path'], 'size_bytes': action['size_bytes'],
        'remaining_gates': (["REGISTER_TRUSTED_DEVICE_SERIAL"] if not identity_ready else []) + [
            'HOST_OWNED_GPIO_TO_EXECUTOR_HANDOFF',
            'LIVE_WRITABLE_MOUNT_ATTESTATION',
            'CRASH_SAFE_EXECUTION_AND_MANIFEST_ORCHESTRATION',
        ],
        'executed': False, 'backup_authorized': False,
    }
