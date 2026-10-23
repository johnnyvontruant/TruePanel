#!/usr/bin/env python3
"""READ-ONLY bidirectional spare-cartridge plan and hardware qualification.

This is deliberately NOT a physical transfer CLI. No live-fire flags, GPIO
arming, mounting, file transfer, or USB mutations are supported here.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from truepanel.cargo.backup_executor import BackupExecutionError, attest_cartridge_read_only
from truepanel.cargo.bidirectional_host_scope import (
    CargoScope, inspect_bidirectional,
)
from tools.loadmaster_spare_batch_live_fire import (
    SPARE_LINK, SPARE_MOUNT, SPARE_SERIAL, SPARE_UUID,
)


def pinned_spare_identity() -> tuple[str, str, bool]:
    """Trusted identity callback for HostBidirectionalApprovalSession.

    Caller must use this for *each* physical arm and confirmation consumption.
    The serial is encoded in the exact registered by-id link, whose resolved
    partition is verified against the mounted exFAT source.
    """
    observation = attest_cartridge_read_only(
        mount=SPARE_MOUNT, registered_uuid=SPARE_UUID, registered_by_id=SPARE_LINK)
    if (not observation.matches_registry or observation.uuid != SPARE_UUID
            or observation.by_id != SPARE_LINK or not observation.read_only):
        raise BackupExecutionError('spare cartridge not hardware-qualified')
    return SPARE_UUID, SPARE_SERIAL, True


def preview(*, nas_root: Path, usb_root: Path,
            entries: tuple[tuple[str, str], ...], recover_verified: bool = False) -> dict:
    """Verify pinned cartridge is RO, then return exact approved directions."""
    if (not nas_root.is_absolute() or not usb_root.is_absolute()
            or '..' in nas_root.parts or '..' in usb_root.parts
            or nas_root.is_symlink() or usb_root.is_symlink()
            or not nas_root.is_dir() or not usb_root.is_dir()):
        raise BackupExecutionError('invalid absolute staging roots')
    nas_resolved = nas_root.resolve(strict=True)
    usb_resolved = usb_root.resolve(strict=True)
    spare_resolved = SPARE_MOUNT.resolve(strict=True)
    if (not nas_resolved.is_relative_to(Path('/mnt/SSDs/'))
            or nas_resolved.is_relative_to(spare_resolved)
            or usb_resolved == spare_resolved
            or not usb_resolved.is_relative_to(spare_resolved)):
        raise BackupExecutionError('spare or SSD staging roots outside designated areas')
    pinned_spare_identity()
    actions = inspect_bidirectional(nas_root=nas_root, usb_root=usb_root,
                                    entries=entries, recover_verified=recover_verified)
    scope = CargoScope('spare-lab', SPARE_UUID, SPARE_SERIAL, actions)
    return {'state': 'READ_ONLY_BIDIRECTIONAL_PREVIEW',
            'schema_version': 1, 'physical_authorized': False,
            'physical_transfer_enabled': False, 'mount_changed': False,
            'cartridge_id': scope.cartridge_id,
            'cartridge_uuid': scope.cartridge_uuid,
            'serial': scope.device_serial, 'batch_digest': scope.digest,
            'recover_verified': recover_verified,
            'actions': [a.__dict__ for a in actions]}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--nas-root', type=Path, required=True)
    parser.add_argument('--usb-root', type=Path, required=True)
    parser.add_argument('--transfer', action='append', required=True,
                        help='DIRECTION:ShowName/filename (repeat for up to 3 files)')
    parser.add_argument('--recover-verified', action='store_true',
                        help='Review already verified published copies only')
    args = parser.parse_args(argv)
    entries = []
    for raw in args.transfer:
        direction, separator, relative = raw.partition(':')
        if not separator or not re.fullmatch('(?:NAS_TO_USB|USB_TO_NAS)', direction):
            parser.error('invalid direction: use NAS_TO_USB: or USB_TO_NAS:')
        entries.append((direction, relative))
    try:
        report = preview(nas_root=args.nas_root, usb_root=args.usb_root,
                         entries=tuple(entries), recover_verified=args.recover_verified)
    except (BackupExecutionError, ValueError) as err:
        print('READ_ONLY_PREFLIGHT_HOLD:', str(err), file=sys.stderr)
        return 1
    print(json.dumps(report, sort_keys=True, indent=2), flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
