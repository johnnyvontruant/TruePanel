#!/usr/bin/env python3
"""Read-only, bounded multi-file Loadmaster candidate inspection.

A batch preview is never physical execution authority. Each file is checked
independently using the existing one-file read-only inspection. This tool
cannot arm GPIO, remount media, or perform copies.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from truepanel.cargo.backup_executor import BackupExecutionError
from truepanel.cargo.physical_transaction_dry_run import inspect_transaction


def preview(*, registry: Path, backlog: Path, cartridge_id: str,
            mount: Path, by_id: str, sources: list[Path]) -> dict:
    if not 1 <= len(sources) <= 3:
        raise BackupExecutionError('preview requires 1 to 3 sources')
    if len({str(path) for path in sources}) != len(sources):
        raise BackupExecutionError('duplicate source refused')
    if any(not path.is_absolute() for path in sources):
        raise BackupExecutionError('all source paths must be absolute')
    inspections = []
    for path in sources:
        result = inspect_transaction(
            registry=registry, backlog=backlog, cartridge_id=cartridge_id,
            mount=mount, by_id=by_id, source_path=path)
        if result['state'] != 'READ_ONLY_TRANSACTION_ACCEPTED':
            raise BackupExecutionError('candidate did not pass read-only check')
        inspections.append(result)
    total = sum(item['size_bytes'] for item in inspections)
    capacity = min(item['available_bytes'] for item in inspections)
    if total > capacity:
        raise BackupExecutionError('batch insufficient cartridge capacity')
    if len({item['destination'] for item in inspections}) != len(inspections):
        raise BackupExecutionError('batch destination collision')
    return {
        'state': 'BATCH_PREVIEW_ONLY', 'cartridge_id': cartridge_id,
        'files': len(inspections), 'total_bytes': total,
        'available_bytes': capacity, 'executed': False,
        'backup_authorized': False,
        'candidates': [
            {'source': item['source'], 'destination': item['destination'],
             'size_bytes': item['size_bytes'],
             'source_sha256': item['source_sha256'],
             'plan_digest': item['plan_digest']}
            for item in inspections
        ],
        'remaining_gates': [
            'BATCH_ATOMICITY_AND_RECOVERY_TESTS',
            'EXPLICIT_BATCH_AUTHORIZATION_AND_EXECUTOR',
            'LIVE_SUPERVISED_BATCH_ACCEPTANCE',
        ],
    }


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--registry', required=True, type=Path)
    p.add_argument('--backlog', required=True, type=Path)
    p.add_argument('--cartridge-id', required=True)
    p.add_argument('--mount', required=True, type=Path)
    p.add_argument('--by-id', required=True)
    p.add_argument('--source', required=True, type=Path, action='append')
    args = p.parse_args()
    print(json.dumps(preview(
        registry=args.registry, backlog=args.backlog,
        cartridge_id=args.cartridge_id, mount=args.mount,
        by_id=args.by_id, sources=args.source), indent=2))


if __name__ == '__main__':
    main()
