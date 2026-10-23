#!/usr/bin/env python3
"""Staging-only, independent RO-only guard. Never mounts RW, never starts a transfer.

--preflight is safe and READ ONLY. --watch is intended only for a dedicated,
separately managed systemd service after human review and qualification.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

from truepanel.cargo.backup_executor import BackupExecutionError
from truepanel.cargo.independent_ro_watchdog import (
    SparePin, guard_loop, host_ro_preflight, mount_mode, owner_start_ticks,
    write_status, same_host_mount_namespace,
)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    exclusive = parser.add_mutually_exclusive_group(required=True)
    exclusive.add_argument('--preflight', action='store_true',
        help='read-only mounted spare/systemd check')
    exclusive.add_argument('--watch', action='store_true',
        help='run in an independently managed systemd service; never remounts rw')
    parser.add_argument('--owner-pid', type=int)
    parser.add_argument('--owner-start-ticks', type=int)
    parser.add_argument('--plan-digest')
    parser.add_argument('--attempt-nonce')
    parser.add_argument('--unit')
    parser.add_argument('--status-file', type=Path)
    parser.add_argument('--lease-seconds', type=int, default=90)
    args = parser.parse_args(argv)

    if args.preflight:
        print(json.dumps(host_ro_preflight(), indent=2))
        return 0

    if os.geteuid() != 0:
        raise BackupExecutionError('only the root-owned independent service may monitor')
    if (args.owner_pid is None or args.owner_start_ticks is None
            or not re.fullmatch(r'[a-f0-9]{64}', args.plan_digest or '')
            or not re.fullmatch(r'[a-f0-9]{32}', args.attempt_nonce or '')
            or args.unit != f'loadmaster-ro-guard-{args.attempt_nonce[:12]}.service'
            or args.status_file is None or not 5 <= args.lease_seconds <= 180
            or args.owner_pid == os.getpid()):
        raise BackupExecutionError('incomplete independent guard launch context')
    if not same_host_mount_namespace(os.getpid()):
        raise BackupExecutionError('guard must share PID 1 host mount namespace')
    if owner_start_ticks(args.owner_pid) != args.owner_start_ticks:
        raise BackupExecutionError('guardian owner process identity changed')
    pin = SparePin()
    if mount_mode(pin) != 'ro':
        raise BackupExecutionError('watchdog launch requires spare read-only')
    issued = time.monotonic()
    boot_id = Path('/proc/sys/kernel/random/boot_id').read_text().strip()

    def report(state):
        payload = {'state': state, 'unit': args.unit,
            'plan_digest': args.plan_digest, 'attempt_nonce': args.attempt_nonce,
            'owner_pid': args.owner_pid, 'owner_ticks': args.owner_start_ticks,
            'guardian_pid': os.getpid(),
            'monotonic_at': time.monotonic(), 'boot_id': boot_id}
        write_status(args.status_file, payload)

    try:
        guard_loop(pin=pin, owner_pid=args.owner_pid,
            owner_ticks=args.owner_start_ticks,
            deadline=issued + args.lease_seconds, report=report)
    except BaseException:
        # Even if monitoring fails unexpectedly, make ONE fail-closed attempt
        # to restore RO *only if the pinned cartridge is still the same device*.
        # If it is absent/swapped, do NOT touch another mount.
        try:
            if mount_mode(pin) == 'rw':
                import subprocess
                subprocess.run(['mount', '-o', 'remount,ro', str(pin.mount)],
                               check=True, capture_output=True, timeout=15)
            if mount_mode(pin) == 'ro':
                report('FAILED_BUT_RO')
            else:
                report('CRITICAL_NOT_RO')
        except BaseException:
            try:
                report('CRITICAL_RO_UNVERIFIED')
            except BaseException:
                pass
        raise
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as error:
        print(f'LOADMASTER_RO_GUARD_HOLD: {type(error).__name__}: {error}', file=sys.stderr)
        sys.exit(2)
