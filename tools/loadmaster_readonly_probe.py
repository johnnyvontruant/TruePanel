#!/usr/bin/env python3
"""Read-only hardware acceptance probe, not a backup executor."""
import argparse
import json
from pathlib import Path
from truepanel.cargo.backup_executor import (
    BackupExecutionError, attest_cartridge_read_only,
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--registry', type=Path, required=True)
    parser.add_argument('--cartridge-id', required=True)
    parser.add_argument('--mount', type=Path, required=True)
    parser.add_argument('--by-id', required=True,
                        help='Previously inspected /dev/disk/by-id/*-partN link')
    args = parser.parse_args()
    try:
        data = json.loads(args.registry.read_text())
        matches = [c for c in data['cartridges'] if c['id'] == args.cartridge_id]
        if len(matches) != 1:
            raise BackupExecutionError('cartridge must match one registry entry')
        entry = matches[0]
        if entry.get('allow_backup') is not False or entry.get('allow_ingest') is not False:
            raise BackupExecutionError('probe requires disabled physical permissions')
        if entry.get('delete_policy') != 'never':
            raise BackupExecutionError('unexpected delete policy')
        evidence = attest_cartridge_read_only(
            mount=args.mount, registered_uuid=entry['uuid'],
            registered_by_id=args.by_id,
        )
        print(json.dumps({
            'state': 'READ_ONLY_IDENTITY_VERIFIED',
            'cartridge_id': args.cartridge_id,
            'mount': evidence.mount,
            'filesystem': evidence.filesystem,
            'uuid': evidence.uuid,
            'by_id': evidence.by_id,
            'read_only': evidence.read_only,
            'executed': False,
            'backup_authorized': False,
        }, indent=2))
    except (BackupExecutionError, OSError, ValueError, KeyError, TypeError) as exc:
        parser.exit(2, f'HOLD: {exc}\n')


if __name__ == '__main__':
    main()
