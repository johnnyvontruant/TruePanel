#!/usr/bin/env python3
"""Supervised, one-shot THREE-file Loadmaster runner for the identified spare.

Default invocation is a READ-ONLY preview. Live mode needs two explicit flags,
exclusive host GPIO ownership, physical Copy press within 30 seconds, and the
existing host-owned durable confirmation journal. No unattended operation.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path

from truepanel.cargo.backup_executor import BackupExecutionError, attest_cartridge_read_only
from truepanel.cargo.batch_authorization import BatchItem, BatchApprovalScope
from truepanel.cargo.batch_host_actuator import execute_host_batch_core
from truepanel.cargo.host_batch_session import HostBatchApprovalSession, HostBatchSpec
from truepanel.cargo.backup_transaction import _safe_parts
from truepanel.cargo.supervised_mount import SupervisedWriteWindow
from truepanel.hardware.fintek_gpio import FintekCopyButtonReader
from truepanel.host.loadmaster_copy_button import LoadmasterCopyButtonService
from truepanel.host.loadmaster_session_bridge import LoadmasterHostSessionBridge
from truepanel.host.ownership import HostOwnershipGuard
from truepanel.cargo.copy_button import DEFAULT_CONFIRMATION_WINDOW_SECONDS

SPARE_SERIAL = '2532EA8D421A'
SPARE_UUID = '6ADA-80D5'
SPARE_LINK = '/dev/disk/by-id/usb-Micron_CT8000X10SSD9_2532EA8D421A-0:0-part2'
SPARE_MOUNT = Path('/mnt/loadmaster-spare-ro')


def sha256_regular(path: Path) -> tuple[int, str]:
    for part in (path, *path.parents):
        if part.is_symlink():
            raise BackupExecutionError('source symlink rejected')
    if not path.is_file():
        raise BackupExecutionError('source missing')
    before = path.stat()
    h = hashlib.sha256()
    with path.open('rb') as stream:
        descriptor_before = os.fstat(stream.fileno())
        if (descriptor_before.st_ino, descriptor_before.st_size) != (before.st_ino, before.st_size):
            raise BackupExecutionError('source changed during open')
        while data := stream.read(1024 * 1024):
            h.update(data)
        descriptor_after = os.fstat(stream.fileno())
    after = path.stat()
    for check in (descriptor_after, after):
        if (check.st_ino, check.st_size, check.st_mtime_ns, check.st_ctime_ns) != (
                before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns):
            raise BackupExecutionError('source mutated during inspection')
    return before.st_size, h.hexdigest()


def snapshot(*, source_root: Path, usb_root: Path, names: tuple[str, ...],
             allow_published: bool = False) -> tuple[BatchItem, ...]:
    if not 1 <= len(names) <= 3 or len(set(names)) != len(names):
        raise BackupExecutionError('requires 1 to 3 unique paths')
    if (not source_root.is_absolute() or not source_root.is_dir()
            or source_root.is_symlink() or not usb_root.is_dir()
            or usb_root.is_symlink()):
        raise BackupExecutionError('invalid source or destination root')
    items = []
    for name in names:
        folder, filename = _safe_parts(name)
        source = source_root / folder / filename
        dest = usb_root / folder / filename
        for candidate in (source.parent, dest.parent, dest):
            if candidate.is_symlink():
                raise BackupExecutionError('unsafe transfer path')
        if not allow_published and os.path.lexists(dest):
            raise BackupExecutionError('destination occupied before authorization')
        size, digest = sha256_regular(source)
        items.append(BatchItem(name, size, digest))
    return tuple(items)


def execute(args) -> int:
    if args.mount != SPARE_MOUNT or args.by_id != SPARE_LINK or args.uuid != SPARE_UUID:
        raise BackupExecutionError('only the verified spare USB device is accepted')
    if (not args.usb_root.is_relative_to(args.mount) or
            args.usb_root == args.mount or
            args.source_root.is_relative_to(args.mount) or
            not args.source_root.is_relative_to(Path('/mnt/SSDs/'))):
        raise BackupExecutionError('unsafe test roots')
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', args.cartridge_id):
        raise BackupExecutionError('invalid cartridge id')
    if args.cartridge_id != 'spare-lab':
        raise BackupExecutionError('non-lab cartridge rejected')
    if args.manifest.is_relative_to(args.mount) or args.journal_root.is_relative_to(args.mount):
        raise BackupExecutionError('host evidence must not reside on cartridge')
    attest_cartridge_read_only(mount=args.mount, registered_uuid=args.uuid,
                               registered_by_id=args.by_id)
    names = tuple(args.relative)
    initial = snapshot(source_root=args.source_root, usb_root=args.usb_root, names=names)
    scope = BatchApprovalScope(cartridge_id=args.cartridge_id,
                               cartridge_uuid=args.uuid, items=initial)
    print(json.dumps({'state':'READ_ONLY_BATCH_READY', 'cartridge_id':args.cartridge_id,
                      'batch_digest':scope.digest, 'files':[i.__dict__ for i in initial],
                      'physical_authorized':False}, indent=2), flush=True)
    if not args.live_fire:
        return 0
    if not args.operator_present:
        raise BackupExecutionError('live fire needs explicit operator-present flag')
    owner = HostOwnershipGuard('loadmaster-spare-three-file-acceptance')
    owner.acquire()
    service = bridge = reader = None
    try:
        args.journal_root.mkdir(parents=True, mode=0o700, exist_ok=True)
        if args.journal_root.is_symlink() or args.journal_root.stat().st_mode & 0o022:
            raise BackupExecutionError('unsafe journal root')
        if not args.manifest.parent.is_dir() or args.manifest.parent.is_symlink():
            raise BackupExecutionError('missing host manifest parent')
        def reattest():
            return snapshot(source_root=args.source_root, usb_root=args.usb_root,
                            names=names, allow_published=True)
        reader = FintekCopyButtonReader()
        service = LoadmasterCopyButtonService(reader=reader)
        session = HostBatchApprovalSession(reattest=reattest)
        bridge = LoadmasterHostSessionBridge(service=service,session=session)
        spec = HostBatchSpec(cartridge_id=args.cartridge_id,
                             cartridge_uuid=args.uuid,device_serial=SPARE_SERIAL,
                             items=initial,journal_root=args.journal_root)
        service.start()
        armed = bridge.prepare_and_arm(spec)
        if armed['plan_digest'] != scope.digest or armed['backup_files'] != len(initial):
            raise BackupExecutionError('host armed unexpected batch')
        print('ARMED: PRESS COPY ONCE NOW. 30-second window. '
              'Spare serial '+SPARE_SERIAL, flush=True)
        deadline = time.monotonic() + DEFAULT_CONFIRMATION_WINDOW_SECONDS - 2
        while not bridge.confirmed:
            if time.monotonic() >= deadline:
                raise BackupExecutionError('Copy confirmation expired; no transfer started')
            if service.snapshot().get('last_error'):
                raise BackupExecutionError('GPIO polling fault')
            time.sleep(0.05)
        print('CONFIRMED: Starting supervised 3-file spare transaction',flush=True)
        result = execute_host_batch_core(
            scope=scope,bridge=bridge,reattest=reattest,
            nas=args.source_root,usb=args.usb_root,mount=args.mount,
            by_id=args.by_id,uuid=args.uuid,manifest=args.manifest,
            writable_session=SupervisedWriteWindow(
                mount=args.mount,uuid=args.uuid,by_id=args.by_id))
        print(json.dumps(result, indent=2), flush=True)
        return 0
    finally:
        try:
            if bridge is not None:
                bridge.disarm()
        finally:
            try:
                if service is not None:
                    service.stop()
            finally:
                if reader is not None:
                    reader.close()
                owner.release()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source-root',type=Path,required=True)
    p.add_argument('--usb-root',type=Path,required=True)
    p.add_argument('--relative',action='append',required=True)
    p.add_argument('--mount',type=Path,default=SPARE_MOUNT)
    p.add_argument('--by-id',default=SPARE_LINK)
    p.add_argument('--uuid',default=SPARE_UUID)
    p.add_argument('--cartridge-id',default='spare-lab')
    p.add_argument('--manifest',type=Path,required=True)
    p.add_argument('--journal-root',type=Path,required=True)
    p.add_argument('--live-fire',action='store_true')
    p.add_argument('--operator-present',action='store_true')
    return execute(p.parse_args())


if __name__=='__main__':
    try:
        sys.exit(main())
    except Exception as exc:
        print('LOADMASTER_BATCH_ABORTED:', type(exc).__name__, str(exc), file=sys.stderr)
        sys.exit(1)
