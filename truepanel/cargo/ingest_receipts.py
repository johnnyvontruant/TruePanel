"""Host-only receipts for USB -> SSD intake, not backup manifest entries.

Import into an actual media library remains a separately reviewed operation.
"""
from __future__ import annotations

import hashlib
import json
import os
import stat
from datetime import datetime, timezone
from pathlib import Path

from .backup_executor import BackupExecutionError
from .bidirectional_host_scope import CargoAction, _stat_and_hash

KIND = 'truepanel.loadmaster.ingest_verified.v1'


def record_verified_ingest(*, receipt_root: Path, cartridge_id: str,
                           cartridge_uuid: str, device_serial: str,
                           action: CargoAction, source: Path, destination: Path) -> dict:
    if (action.direction != 'USB_TO_NAS' or not receipt_root.is_absolute() or
            receipt_root.is_symlink() or not receipt_root.is_dir() or
            not receipt_root.is_relative_to(Path('/mnt/SSDs/')) or
            any(p.is_symlink() for p in receipt_root.parents) or
            any(p.is_symlink() for p in (source, destination, *source.parents, *destination.parents)) or
            not destination.is_relative_to(Path('/mnt/SSDs/')) or
            receipt_root.is_relative_to(Path('/mnt/loadmaster-spare-ro')) or
            not source.is_absolute() or not destination.is_absolute()):
        raise BackupExecutionError('unsafe ingest receipt context')
    root_stat = receipt_root.stat()
    if (root_stat.st_mode & 0o022 or not stat.S_ISDIR(root_stat.st_mode)):
        raise BackupExecutionError('ingest receipt root is not private')
    for path in (source, destination):
        if _stat_and_hash(path) != (action.size_bytes, action.sha256):
            raise BackupExecutionError('ingest receipt verification failed')
    claim = {'kind': KIND, 'cartridge_id': cartridge_id,
             'cartridge_uuid': cartridge_uuid, 'device_serial': device_serial,
             'direction': action.direction, 'relative_path': action.relative_path,
             'size_bytes': action.size_bytes, 'sha256': action.sha256,
             'source': str(source), 'destination': str(destination)}
    key = hashlib.sha256(json.dumps(claim, sort_keys=True).encode()).hexdigest()
    receipt = receipt_root / (key + '.json')
    payload = {**claim, 'verified_at': datetime.now(timezone.utc).isoformat()}
    try:
        fd = os.open(receipt, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                     os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
    except FileExistsError:
        if receipt.is_symlink():
            raise BackupExecutionError('unsafe existing ingest receipt')
        try:
            previous = json.loads(receipt.read_text())
        except (ValueError, OSError) as exc:
            raise BackupExecutionError('unreadable existing ingest receipt') from exc
        if any(previous.get(k) != v for k, v in claim.items()):
            raise BackupExecutionError('conflicting ingest receipt')
        return {'state': 'ALREADY_RECORDED', 'receipt': str(receipt)}
    try:
        with os.fdopen(fd, 'w') as stream:
            stream.write(json.dumps(payload, sort_keys=True) + '\n')
            stream.flush()
            os.fsync(stream.fileno())
        directory_fd = os.open(receipt_root, os.O_DIRECTORY | os.O_RDONLY | os.O_NOFOLLOW)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except Exception:
        # Preserve any created receipt on failure; never silently make replay possible.
        raise
    return {'state': 'INGEST_EVIDENCE_RECORDED', 'receipt': str(receipt)}
