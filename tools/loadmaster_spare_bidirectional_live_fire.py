#!/usr/bin/env python3
"""One-shot, operator-attended mixed-direction spare-cartridge acceptance.

Default: READ-ONLY preview. --live-fire requires --operator-present plus
exclusive GPIO ownership (production truepanel.service must be stopped).
Never imports directly to the media library; SSD acceptance folder only.
The independent RO watchdog and separate RO rescue are mandatory before RW.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import stat
import subprocess
import sys
import time
from pathlib import Path

from truepanel.cargo.backup_executor import BackupExecutionError
from truepanel.cargo.bidirectional_host_scope import (
    CargoScope, HostBidirectionalApprovalSession, inspect_bidirectional,
)
from truepanel.cargo.copy_button import DEFAULT_CONFIRMATION_WINDOW_SECONDS
from truepanel.cargo.independent_ro_watchdog import (
    SparePin, mount_mode, owner_start_ticks, verify_independent_guard,
)
from truepanel.cargo.ingest_receipts import record_verified_ingest
from truepanel.cargo.supervised_bidirectional_batch import execute_supervised_bidirectional_batch
from truepanel.cargo.supervised_mount import SupervisedWriteWindow
from truepanel.hardware.fintek_gpio import FintekCopyButtonReader
from truepanel.host.loadmaster_copy_button import LoadmasterCopyButtonService
from truepanel.host.loadmaster_session_bridge import LoadmasterHostSessionBridge
from truepanel.host.ownership import HostOwnershipGuard
from tools.loadmaster_spare_bidirectional_preview import (
    SPARE_LINK, SPARE_MOUNT, SPARE_SERIAL, SPARE_UUID, pinned_spare_identity,
)

STAGE = Path('/mnt/SSDs/Applications/TruePanel-Executor-Stage')
STATE = Path('/mnt/SSDs/Applications/Loadmaster-Watchdog-Qualification')
NAS = Path('/mnt/SSDs/Applications/Loadmaster-Bidirectional-Acceptance-20261023')
USB = SPARE_MOUNT / 'LOADMASTER-LAB-20261022'
EXPORT = ('NAS_TO_USB', 'Outbound Acceptance/episode.mkv')
INGEST = ('USB_TO_NAS', 'Synthetic Show 1/episode-1.mkv')
ENTRIES = (EXPORT, INGEST)
LEASE_SECONDS = 90
RESCUE_SECONDS = 120


def _call(argv: list[str], *, timeout: int = 12) -> str:
    return subprocess.check_output(argv, text=True, stderr=subprocess.STDOUT,
                                   timeout=timeout).strip()


def _private_folder(folder: Path) -> None:
    if not folder.is_absolute() or not folder.is_relative_to(STATE):
        raise BackupExecutionError('acceptance state must be under dedicated SSD state')
    if any(x.is_symlink() for x in (folder, *folder.parents)):
        raise BackupExecutionError('symlinked acceptance state')
    if not folder.is_dir():
        raise BackupExecutionError('missing acceptance state directory; create as root 0700')
    info = folder.stat()
    if info.st_uid != 0 or info.st_mode & 0o077 or not stat.S_ISDIR(info.st_mode):
        raise BackupExecutionError('acceptance state must be root-owned 0700')


def _preflight(*, recover: bool) -> CargoScope:
    if os.geteuid() != 0:
        raise BackupExecutionError('root required for pinned spare qualification')
    if not STAGE.is_dir() or not NAS.is_dir() or not USB.is_dir():
        raise BackupExecutionError('expected fixed acceptance directories missing')
    if NAS.is_symlink() or USB.is_symlink() or NAS == USB:
        raise BackupExecutionError('unsafe acceptance roots')
    if pinned_spare_identity() != (SPARE_UUID, SPARE_SERIAL, True):
        raise BackupExecutionError('spare is not the exact known read-only cartridge')
    if mount_mode(SparePin()) != 'ro':
        raise BackupExecutionError('pinned spare must be read-only')
    for service in ('truepanel-mission-control.service',):
        if not _service_active(service):
            raise BackupExecutionError('production Mission Control not active')
    fresh = inspect_bidirectional(nas_root=NAS, usb_root=USB, entries=ENTRIES,
                                  recover_verified=recover)
    if len(fresh) != 2 or {a.direction for a in fresh} != {'NAS_TO_USB', 'USB_TO_NAS'}:
        raise BackupExecutionError('requires exactly one export and one ingest')
    return CargoScope('spare-lab', SPARE_UUID, SPARE_SERIAL, fresh)


def _service_active(unit: str) -> bool:
    completed = subprocess.run(
        ['systemctl', 'is-active', unit], capture_output=True,
        text=True, timeout=8, check=False)
    return completed.returncode == 0 and completed.stdout.strip() == 'active'


def _state_unit_fields(unit: str) -> dict[str, str]:
    output = _call(['systemctl', 'show', unit, '--property=ActiveState,MainPID,LoadState'])
    return dict(line.split('=', 1) for line in output.splitlines() if '=' in line)


def _start_guard(scope: CargoScope, folder: Path):
    """Start independent host namespace guard and RO-only timed rescue.

    Called only after real Copy press and before the writable remount.
    """
    nonce = scope.attempt_nonce
    unit = 'loadmaster-ro-guard-' + nonce[:12] + '.service'
    rescue = 'loadmaster-ro-rescue-' + nonce[:12]
    status = folder / (nonce + '.json')
    owner_pid = os.getpid()
    ticks = owner_start_ticks(owner_pid)
    if mount_mode(SparePin()) != 'ro':
        raise BackupExecutionError('cannot start guard from writable mount')
    _call([
        'systemd-run', '--unit=' + unit,
        '--property=WorkingDirectory=' + str(STAGE),
        '--property=Restart=no', '--property=NoNewPrivileges=yes',
        '/usr/bin/python3', '-m', 'tools.loadmaster_spare_ro_guard',
        '--watch', '--owner-pid', str(owner_pid),
        '--owner-start-ticks', str(ticks), '--plan-digest', scope.digest,
        '--attempt-nonce', nonce, '--unit', unit, '--status-file', str(status),
        '--lease-seconds', str(LEASE_SECONDS),
    ])

    def verified() -> bool:
        return verify_independent_guard(
            path=status, plan_digest=scope.digest, attempt_nonce=nonce,
            owner_pid=owner_pid, owner_ticks=ticks, unit=unit)

    end = time.monotonic() + 8
    while not verified():
        if time.monotonic() >= end:
            raise BackupExecutionError('independent watchdog never became READY')
        time.sleep(0.12)
    # A distinct systemd timer will attempt *only* RO if the watchdog fails.
    _call([
        'systemd-run', '--unit=' + rescue,
        '--on-active=' + str(RESCUE_SECONDS) + 's',
        '--property=WorkingDirectory=' + str(STAGE),
        '/usr/bin/python3', str(STAGE / 'tools/loadmaster_ro_rw_qualification.py'),
        '--rescue',
    ])
    fields = _state_unit_fields(rescue + '.timer')
    if fields.get('ActiveState') != 'active' or fields.get('LoadState') != 'loaded':
        raise BackupExecutionError('independent RO rescue timer missing')
    if not verified() or mount_mode(SparePin()) != 'ro':
        raise BackupExecutionError('watchdog or cartridge changed after rescue arm')
    return unit, verified


def execute(*, live: bool, operator_present: bool, recover_verified: bool) -> int:
    scope = _preflight(recover=recover_verified)
    manifest_dir = STATE / 'checkpoint11-acceptance'
    if live:
        _private_folder(STATE)
        _private_folder(manifest_dir)
    print(json.dumps({
        'state': 'READ_ONLY_MIXED_BATCH_READY',
        'cartridge_serial': SPARE_SERIAL, 'uuid': SPARE_UUID,
        'nas_root': str(NAS), 'usb_root': str(USB),
        'plan_digest': scope.digest, 'files': [a.__dict__ for a in scope.actions],
        'physical_authorized': False, 'live_fire_requested': live,
    }, indent=2), flush=True)
    if not live:
        return 0
    if not operator_present:
        raise BackupExecutionError('live mode requires separate --operator-present flag')
    if _service_active('truepanel.service'):
        raise BackupExecutionError('host GPIO occupied: truepanel.service must be safely stopped')
    if not (STAGE / 'tools/loadmaster_ro_rw_qualification.py').is_file():
        raise BackupExecutionError('independent rescue program missing')
    if not _service_active('truepanel-mission-control.service'):
        raise BackupExecutionError('Mission Control unexpectedly unavailable')

    # Existing tested hardware ownership + polling + durable approval bridge.
    ownership = HostOwnershipGuard('loadmaster-spare-bidirectional-final')
    ownership.acquire()
    reader = service = bridge = None
    try:
        reader = FintekCopyButtonReader()
        service = LoadmasterCopyButtonService(reader=reader)
        session = HostBidirectionalApprovalSession(
            fresh_actions=lambda: inspect_bidirectional(
                nas_root=NAS, usb_root=USB, entries=ENTRIES,
                recover_verified=recover_verified),
            attest_identity=pinned_spare_identity)
        bridge = LoadmasterHostSessionBridge(service=service, session=session)
        service.start()
        armed = bridge.prepare_and_arm((scope, manifest_dir))
        if armed.get('plan_digest') != scope.digest or armed.get('backup_files') != 2:
            raise BackupExecutionError('unexpected GPIO-armed plan')
        print('ARMED: PRESS LOWER COPY BUTTON ONCE NOW (30-second window)', flush=True)
        deadline = time.monotonic() + DEFAULT_CONFIRMATION_WINDOW_SECONDS - 2
        while not bridge.confirmed:
            if time.monotonic() >= deadline:
                raise BackupExecutionError('Copy confirmation expired without transfer')
            if service.snapshot().get('last_error'):
                raise BackupExecutionError('GPIO reader failed')
            time.sleep(0.05)
        print('CONFIRMED: starting independent watchdog and RO-only rescue', flush=True)
        unit, guard_verified = _start_guard(scope, manifest_dir)
        print('WATCHDOG READY:', unit, flush=True)

        def record_ingest(action, source, destination):
            return record_verified_ingest(
                receipt_root=manifest_dir, cartridge_id=scope.cartridge_id,
                cartridge_uuid=scope.cartridge_uuid, device_serial=scope.device_serial,
                action=action, source=source, destination=destination)

        result = execute_supervised_bidirectional_batch(
            scope=scope, bridge=bridge, nas_root=NAS, usb_root=USB,
            mount=SPARE_MOUNT, by_id=SPARE_LINK, uuid=SPARE_UUID,
            device_serial=SPARE_SERIAL,
            backup_manifest=manifest_dir / 'backup-manifest.json',
            record_ingest=record_ingest,
            writable_session=SupervisedWriteWindow(
                mount=SPARE_MOUNT, uuid=SPARE_UUID, by_id=SPARE_LINK),
            attest_read_only=pinned_spare_identity,
            watchdog_verified=guard_verified)
        if mount_mode(SparePin()) != 'ro':
            raise BackupExecutionError('CRITICAL: postflight cartridge not RO')
        print(json.dumps(result, indent=2), flush=True)
        print('FINAL_BIDIRECTIONAL_ACCEPTANCE_PASS', flush=True)
        return 0
    finally:
        if bridge is not None:
            bridge.disarm()
        if service is not None:
            service.stop()
        if reader is not None:
            reader.close()
        ownership.release()
        # NEVER stop any independent guardian or rescue timer while the USB
        # state is writable or unknown. Owner exit activates emergency RO.


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live-fire', action='store_true')
    parser.add_argument('--operator-present', action='store_true')
    parser.add_argument('--recover-verified', action='store_true')
    args = parser.parse_args(argv)
    try:
        return execute(live=args.live_fire, operator_present=args.operator_present,
                       recover_verified=args.recover_verified)
    except Exception as err:
        print('BIDIRECTIONAL_ACCEPTANCE_HOLD:', type(err).__name__, str(err),
              file=sys.stderr, flush=True)
        return 2


if __name__ == '__main__':
    sys.exit(main())
