"""Non-actuating, batch-scoped approval contract for a future host executor.

A physical Copy confirmation only approves the *exact* ordered bounded
manifest. This module cannot trigger GPIO, mount disks, or perform IO.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import PurePosixPath

from .backup_executor import BackupExecutionError


@dataclass(frozen=True)
class BatchItem:
    relative_path: str
    size_bytes: int
    sha256: str


def batch_digest(*, cartridge_id: str, cartridge_uuid: str,
                 items: tuple[BatchItem, ...]) -> str:
    if not cartridge_id or not cartridge_uuid or not 1 <= len(items) <= 3:
        raise BackupExecutionError('invalid batch scope')
    seen = set()
    records = []
    for item in items:
        if type(item) is not BatchItem or type(item.size_bytes) is not int or item.size_bytes < 0:
            raise BackupExecutionError('invalid batch item')
        path = item.relative_path
        if (not isinstance(path, str) or not path or len(PurePosixPath(path).parts) != 2
                or PurePosixPath(path).is_absolute() or path != str(PurePosixPath(path))
                or any(part in ('', '.', '..') for part in path.split('/'))
                or chr(92) in path or chr(0) in path or path in seen):
            raise BackupExecutionError('unsafe or duplicate batch path')
        seen.add(path)
        if (not isinstance(item.sha256, str) or len(item.sha256) != 64 or
                any(ch not in '0123456789abcdef' for ch in item.sha256)):
            raise BackupExecutionError('invalid batch hash')
        records.append({'relative_path': path, 'size_bytes': item.size_bytes,
                        'sha256': item.sha256})
    payload = {'contract': 'truepanel.loadmaster.batch.v1',
               'cartridge_id': cartridge_id, 'cartridge_uuid': cartridge_uuid,
               'items': records}
    return hashlib.sha256(json.dumps(payload, sort_keys=True,
                                     separators=(',', ':')).encode()).hexdigest()


class BatchApprovalScope:
    """Bind one consumed host approval to one immutable batch, one time."""

    def __init__(self, *, cartridge_id: str, cartridge_uuid: str,
                 items: tuple[BatchItem, ...]):
        self.cartridge_id = cartridge_id
        self.cartridge_uuid = cartridge_uuid
        self.items = items
        self.digest = batch_digest(cartridge_id=cartridge_id,
                                   cartridge_uuid=cartridge_uuid, items=items)
        self._spent = False

    def consume(self, *, host_evidence: dict, fresh_digest: str) -> tuple[BatchItem, ...]:
        # Burn process-local scope even if validation fails. Durable host journal
        # must already have consumed the actual physical button confirmation.
        if self._spent:
            raise BackupExecutionError('batch scope already spent')
        self._spent = True
        if (type(host_evidence) is not dict or
                host_evidence.get('state') != 'HOST_APPROVAL_EVIDENCE_ONLY' or
                host_evidence.get('physical_execution_enabled') is not False or
                host_evidence.get('executed') is not False or
                host_evidence.get('cartridge_id') != self.cartridge_id or
                host_evidence.get('plan_digest') != self.digest or
                fresh_digest != self.digest):
            raise BackupExecutionError('batch approval scope mismatch')
        return self.items
