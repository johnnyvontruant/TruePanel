#!/usr/bin/env python3
"""Checkpoint 10A: real independent systemd watchdog, READ-ONLY only.

Creates a synthetic owner (sleep) and a transient guard systemd service, verifies
actual independent service identity and fresh status, SIGKILLs only the synthetic
owner, then confirms the guard exits with the pinned USB still read-only.
Never mounts USB read-write, arms GPIO, or runs a transfer.
"""
from __future__ import annotations

import hashlib
import json
import os
import secrets
import shutil
import stat
import subprocess
import sys
import time
from pathlib import Path

STAGE = Path('/mnt/SSDs/Applications/TruePanel-Executor-Stage')
STATE = Path('/mnt/SSDs/Applications/Loadmaster-Watchdog-Qualification')


def run(args: list[str], *, timeout: int = 10) -> str:
    return subprocess.check_output(args, text=True, stderr=subprocess.STDOUT,
                                   timeout=timeout).strip()


def check_state_directory() -> None:
    if not STATE.exists():
        STATE.mkdir(mode=0o700)
    info = STATE.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o077:
        raise RuntimeError('HOLD: Watchdog state directory must be root-owned mode 0700')


def unit_fields(unit: str) -> dict[str, str]:
    raw = run(['systemctl', 'show', unit,
               '--property=ActiveState,MainPID,Result,ExecMainStatus,LoadState'])
    return dict(line.split('=', 1) for line in raw.splitlines() if '=' in line)


def main() -> int:
    if os.geteuid() != 0:
        raise RuntimeError('HOLD: run as root on BattleStation')
    if not STAGE.is_dir():
        raise RuntimeError('HOLD: staged executor path is missing')
    os.chdir(STAGE)
    from truepanel.cargo.independent_ro_watchdog import (
        SparePin, mount_mode, owner_start_ticks, verify_independent_guard,
    )
    if run(['systemctl', 'is-active', 'truepanel.service']) != 'active' or \
       run(['systemctl', 'is-active', 'truepanel-mission-control.service']) != 'active':
        raise RuntimeError('HOLD: production service is inactive')
    if mount_mode(SparePin()) != 'ro':
        raise RuntimeError('HOLD: spare cartridge is not pinned and read-only')
    if not shutil.which('systemd-run') or not shutil.which('sleep'):
        raise RuntimeError('HOLD: systemd-run or sleep is missing')
    check_state_directory()

    nonce = secrets.token_hex(16)
    digest = hashlib.sha256(('READ_ONLY_QUALIFICATION_' + nonce).encode()).hexdigest()
    unit = f'loadmaster-ro-guard-{nonce[:12]}.service'
    status_path = STATE / f'{nonce}.json'
    owner = None
    started = False
    try:
        owner = subprocess.Popen([shutil.which('sleep'), '40'],
                                 stdin=subprocess.DEVNULL,
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        ticks = owner_start_ticks(owner.pid)
        cmd = [
            'systemd-run', '--unit=' + unit,
            '--property=WorkingDirectory=' + str(STAGE),
            '--property=Restart=no', '--property=PrivateMounts=no',
            '--property=NoNewPrivileges=yes',
            '/usr/bin/python3', '-m', 'tools.loadmaster_spare_ro_guard',
            '--watch', '--owner-pid', str(owner.pid),
            '--owner-start-ticks', str(ticks), '--plan-digest', digest,
            '--attempt-nonce', nonce, '--unit', unit,
            '--status-file', str(status_path), '--lease-seconds', '30',
        ]
        print('=== LAUNCH INDEPENDENT SYSTEMD GUARD (NO USB WRITES) ===', flush=True)
        print(run(cmd), flush=True)
        started = True
        ready = False
        end = time.monotonic() + 10
        while time.monotonic() < end:
            if verify_independent_guard(path=status_path, plan_digest=digest,
                                        attempt_nonce=nonce, owner_pid=owner.pid,
                                        owner_ticks=ticks, unit=unit):
                ready = True
                break
            time.sleep(0.2)
        if not ready:
            raise RuntimeError('HOLD: independent guard never became verified READY')
        fields = unit_fields(unit)
        if fields.get('ActiveState') != 'active':
            raise RuntimeError('HOLD: guard unit unexpectedly inactive')
        print('PASS: independent systemd MainPID, live boot, fresh status, and owner binding', flush=True)
        print('=== SIMULATE TRANSFER OWNER SIGKILL (SYNTHETIC OWNER ONLY) ===', flush=True)
        owner.kill()
        owner.wait(timeout=4)
        finish = time.monotonic() + 10
        restored = False
        while time.monotonic() < finish:
            if status_path.is_file():
                data = json.loads(status_path.read_text())
                if data.get('state') == 'RESTORED_RO':
                    restored = True
                    break
            time.sleep(0.2)
        if not restored:
            raise RuntimeError('HOLD: guardian did not record RESTORED_RO')
        finish = time.monotonic() + 5
        fields = {}
        while time.monotonic() < finish:
            fields = unit_fields(unit)
            if fields.get('ActiveState') != 'active':
                break
            time.sleep(0.2)
        if (fields.get('ActiveState') != 'inactive' or
                fields.get('Result') != 'success' or
                fields.get('ExecMainStatus') != '0'):
            raise RuntimeError('HOLD: guardian service exit was not successful: ' + str(fields))
        if mount_mode(SparePin()) != 'ro':
            raise RuntimeError('CRITICAL: spare not confirmed read-only after guardian exit')
        print('PASS: synthetic owner SIGKILL detected; guard exited successfully', flush=True)
        print('PASS: exact spare USB still read-only', flush=True)
        print('PASS: no USB write, remount-rw, GPIO, or transfer attempted', flush=True)
        print('=== FINAL ===', flush=True)
        print(json.dumps({'state': 'INDEPENDENT_RO_ONLY_GUARD_QUALIFIED',
                          'unit': unit, 'test': 'synthetic-owner-SIGKILL-while-RO',
                          'postflight_mount_mode': 'ro', 'physical_rw_restoration_tested': False},
                         indent=2), flush=True)
        return 0
    finally:
        if owner is not None and owner.poll() is None:
            owner.kill()
            owner.wait(timeout=5)
        if started:
            try:
                mode = mount_mode(SparePin())
                if mode == 'ro' and unit_fields(unit).get('ActiveState') == 'active':
                    # On a clean RO mount, no reason to keep a qualification guard around.
                    subprocess.run(['systemctl', 'stop', unit], timeout=8, check=False)
                elif mode != 'ro':
                    print('CRITICAL: USB not RO; leaving watchdog service running for recovery',
                          file=sys.stderr)
            except Exception as e:
                print('CRITICAL: could not verify cleanup safety; inspect guard unit: ' +
                      unit + ': ' + str(e), file=sys.stderr)


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as exc:
        print(f'LOADMASTER_GUARD_QUALIFICATION_HOLD: {type(exc).__name__}: {exc}',
              file=sys.stderr)
        sys.exit(2)
