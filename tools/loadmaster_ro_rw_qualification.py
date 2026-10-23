#!/usr/bin/env python3
"""Loadmaster Checkpoint 10B: bounded live spare RW -> independent RO recovery.

Default --preflight is READ-ONLY. --live-rw is an explicit hardware mutation test
on ONLY the pinned spare exFAT mount; it copies/deletes no media. It starts both
an independently verified PID-bound watchdog and an independent timed RO rescue
BEFORE making the USB mount writable. It SIGKILLs only a synthetic `sleep` owner.
Never install into production or use with a real media cartridge.
"""
from __future__ import annotations

import argparse
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
PYTHON = '/usr/bin/python3'
GUARD_LEASE = 35
RESCUE_DELAY = '45s'


def call(args: list[str], *, timeout: int = 12) -> str:
    return subprocess.check_output(args, text=True, stderr=subprocess.STDOUT,
                                   timeout=timeout).strip()


def unit_fields(unit: str) -> dict[str, str]:
    raw = call(['systemctl', 'show', unit,
                '--property=ActiveState,MainPID,Result,ExecMainStatus,LoadState'])
    return dict(line.split('=', 1) for line in raw.splitlines() if '=' in line)


def requires_private_state() -> None:
    info = STATE.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o077:
        raise RuntimeError('HOLD: qualification state directory must be root-owned 0700')


def get_modules():
    if os.geteuid() != 0:
        raise RuntimeError('HOLD: root required on BattleStation')
    if not STAGE.is_dir() or not (STAGE / 'truepanel/cargo/independent_ro_watchdog.py').is_file():
        raise RuntimeError('HOLD: staged watchdog source missing')
    os.chdir(STAGE)
    if str(STAGE) not in sys.path:
        sys.path.insert(0, str(STAGE))
    from truepanel.cargo.independent_ro_watchdog import (
        SparePin, mount_mode, owner_start_ticks, verify_independent_guard,
    )
    return SparePin, mount_mode, owner_start_ticks, verify_independent_guard


def verify_baseline(SparePin, mount_mode) -> None:
    requires_private_state()
    for service in ('truepanel.service', 'truepanel-mission-control.service'):
        if call(['systemctl', 'is-active', service]) != 'active':
            raise RuntimeError('HOLD: production service not active: ' + service)
    if mount_mode(SparePin()) != 'ro':
        raise RuntimeError('HOLD: exact spare not mounted read-only')
    for cmd in ('systemctl', 'systemd-run', 'mount', 'findmnt', 'sleep'):
        if not shutil.which(cmd):
            raise RuntimeError('HOLD: missing required command: ' + cmd)


def rescue_only() -> int:
    """Independently launched, RO-only failsafe. It NEVER requests RW."""
    SparePin, mount_mode, _, _ = get_modules()
    from truepanel.cargo.independent_ro_watchdog import same_host_mount_namespace
    if not same_host_mount_namespace(os.getpid()):
        raise RuntimeError('CRITICAL: rescue is outside the host mount namespace')
    mode = mount_mode(SparePin())
    if mode == 'rw':
        subprocess.run(['mount', '-o', 'remount,ro', str(SparePin().mount)],
                       timeout=15, check=True)
    final = mount_mode(SparePin())
    if final != 'ro':
        raise RuntimeError('CRITICAL: rescue could not prove exact spare RO')
    print('LOADMASTER_RO_RESCUE_VERIFIED: pinned spare ro', flush=True)
    return 0


def inspect_only() -> int:
    SparePin, mount_mode, _, _ = get_modules()
    verify_baseline(SparePin, mount_mode)
    print(json.dumps({
        'state': 'SPARE_RW_RECOVERY_PREFLIGHT_PASS',
        'spare_serial': SparePin().serial,
        'spare_uuid': SparePin().uuid,
        'mount': str(SparePin().mount),
        'mount_mode': 'ro',
        'services': 'both active',
        'physical_rw_test_performed': False,
        'requires_separate_explicit_live_rw_command': True,
    }, indent=2), flush=True)
    return 0


def live_rw_test(*, read_only_qualification: bool = False) -> int:
    SparePin, mount_mode, owner_start_ticks, verify_guard = get_modules()
    verify_baseline(SparePin, mount_mode)
    nonce = secrets.token_hex(16)
    digest = hashlib.sha256(('EXPLICIT_LIVE_RW_QUALIFICATION_' + nonce).encode()).hexdigest()
    unit = 'loadmaster-ro-guard-' + nonce[:12] + '.service'
    rescue_unit = 'loadmaster-ro-rescue-' + nonce[:12]
    rescue_timer = rescue_unit + '.timer'
    status = STATE / (nonce + '.json')
    owner = None
    guard_started = False
    rescue_armed = False
    ever_rw = False
    try:
        owner = subprocess.Popen([shutil.which('sleep'), '90'],
                                 stdin=subprocess.DEVNULL,
                                 stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL)
        ticks = owner_start_ticks(owner.pid)
        guard_args = [
            'systemd-run', '--unit=' + unit,
            '--property=WorkingDirectory=' + str(STAGE),
            '--property=Restart=no', '--property=PrivateMounts=no',
            '--property=NoNewPrivileges=yes',
            PYTHON, '-m', 'tools.loadmaster_spare_ro_guard', '--watch',
            '--owner-pid', str(owner.pid), '--owner-start-ticks', str(ticks),
            '--plan-digest', digest, '--attempt-nonce', nonce,
            '--unit', unit, '--status-file', str(status),
            '--lease-seconds', str(GUARD_LEASE),
        ]
        print('=== START INDEPENDENT GUARD WHILE USB IS RO ===', flush=True)
        print(call(guard_args), flush=True)
        guard_started = True
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            if verify_guard(path=status, plan_digest=digest,
                            attempt_nonce=nonce, owner_pid=owner.pid,
                            owner_ticks=ticks, unit=unit):
                break
            time.sleep(0.15)
        else:
            raise RuntimeError('HOLD: watchdog not independently READY')
        print('PASS: guarded service independently READY', flush=True)

        if read_only_qualification:
            print('=== QUALIFY GUARD IN HOST MOUNT NAMESPACE (NO RW) ===', flush=True)
            owner.kill()
            owner.wait(timeout=4)
            expire = time.monotonic() + 15
            while time.monotonic() < expire:
                if status.is_file():
                    try:
                        if json.loads(status.read_text()).get('state') == 'RESTORED_RO':
                            break
                    except (OSError, ValueError):
                        pass
                time.sleep(0.15)
            else:
                raise RuntimeError('HOLD: host-namespace guard did not report RO')
            if mount_mode(SparePin()) != 'ro':
                raise RuntimeError('CRITICAL: host did not independently verify RO')
            finish = time.monotonic() + 5
            fields = unit_fields(unit)
            while fields.get('ActiveState') == 'active' and time.monotonic() < finish:
                time.sleep(0.15)
                fields = unit_fields(unit)
            if fields.get('Result') != 'success' or fields.get('ExecMainStatus') != '0':
                raise RuntimeError('HOLD: guard exit result unverified: ' + str(fields))
            print(json.dumps({'state': 'HOST_NAMESPACE_RO_GUARD_QUALIFIED',
                'mount_mode': 'ro', 'went_rw': False,
                'independent_guard_host_namespace': True}, indent=2), flush=True)
            return 0

        # This second, distinct systemd timer is the emergency read-only backstop.
        # Its command resolves identity via SparePin before touching any mount.
        print('=== ARM INDEPENDENT TIMED READ-ONLY RESCUE ===', flush=True)
        print(call([
            'systemd-run', '--unit=' + rescue_unit,
            '--on-active=' + RESCUE_DELAY,
            '--property=WorkingDirectory=' + str(STAGE),
            PYTHON, str(STAGE / 'tools/loadmaster_ro_rw_qualification.py'),
            '--rescue',
        ]), flush=True)
        rescue_armed = True
        timer_state = unit_fields(rescue_timer)
        if timer_state.get('ActiveState') != 'active' or timer_state.get('LoadState') != 'loaded':
            raise RuntimeError('HOLD: independent RO rescue timer not confirmed active')
        if not verify_guard(path=status, plan_digest=digest,
                            attempt_nonce=nonce, owner_pid=owner.pid,
                            owner_ticks=ticks, unit=unit):
            raise RuntimeError('HOLD: watchdog readiness became stale')
        if mount_mode(SparePin()) != 'ro':
            raise RuntimeError('HOLD: spare changed before RW window')
        print('PASS: independent RO backstop armed', flush=True)

        # ONLY intended writable-mount mutation. No file writes, rsync or GPIO.
        print('=== BEGIN SHORT, EXPLICIT LIVE RW RESTORATION TEST ===', flush=True)
        subprocess.run(['mount', '-o', 'remount,rw', str(SparePin().mount)],
                       timeout=10, check=True)
        ever_rw = True
        if mount_mode(SparePin()) != 'rw':
            raise RuntimeError('CRITICAL: RW remount not independently verifiable')
        print('PASS: verified pinned spare temporarily RW', flush=True)

        print('=== KILL SYNTHETIC OWNER, NOT WATCHDOG ===', flush=True)
        owner.kill()
        owner.wait(timeout=4)
        deadline = time.monotonic() + 20
        restored = False
        while time.monotonic() < deadline:
            if status.is_file():
                try:
                    record = json.loads(status.read_text())
                    if record.get('state') == 'RESTORED_RO':
                        restored = True
                        break
                    if str(record.get('state', '')).startswith('CRITICAL'):
                        break
                except (OSError, ValueError):
                    pass
            time.sleep(0.15)
        if not restored:
            raise RuntimeError('CRITICAL: guardian did not record verified RO recovery')
        if mount_mode(SparePin()) != 'ro':
            raise RuntimeError('CRITICAL: external RO reattestation failed')
        fields = unit_fields(unit)
        finish = time.monotonic() + 5
        while fields.get('ActiveState') == 'active' and time.monotonic() < finish:
            time.sleep(0.15)
            fields = unit_fields(unit)
        if fields.get('Result') != 'success' or fields.get('ExecMainStatus') != '0':
            raise RuntimeError('HOLD: guard exit result unverified: ' + str(fields))
        print(json.dumps({
            'state': 'INDEPENDENT_RW_TO_RO_RECOVERY_QUALIFIED',
            'spare_uuid': SparePin().uuid,
            'guardian_unit': unit,
            'owner': 'synthetic-only-SIGKILL',
            'went_rw': True,
            'watchdog_reported_restored_ro': True,
            'postflight_mount_mode': 'ro',
            'independent_rescue_timer': rescue_timer,
            'media_transfer_performed': False,
            'gpio_pressed': False,
        }, indent=2), flush=True)
        return 0
    finally:
        if owner is not None and owner.poll() is None:
            owner.kill()
            owner.wait(timeout=5)
        # Never stop an active watchdog if the cartridge remains RW or unverified.
        try:
            current = mount_mode(SparePin())
            if current != 'ro':
                print('CRITICAL: spare not RO; independent guard and rescue remain armed!',
                      file=sys.stderr)
                # At this point the owner is dead, so the guard should restore RO.
                # A direct restoration attempt provides an additional defense.
                subprocess.run(['mount', '-o', 'remount,ro', str(SparePin().mount)],
                               timeout=15, check=False)
                current = mount_mode(SparePin())
            if current == 'ro':
                if guard_started and unit_fields(unit).get('ActiveState') == 'active':
                    subprocess.run(['systemctl', 'stop', unit], check=False, timeout=6)
                print('POSTFLIGHT: pinned spare read-only', flush=True)
            else:
                print('CRITICAL: failed to confirm RO; inspect systemd rescue timer ' +
                      rescue_timer, file=sys.stderr)
        except Exception as exc:
            print('CRITICAL: could not reattest pinned spare: ' + str(exc), file=sys.stderr)
        if not rescue_armed and ever_rw:
            print('CRITICAL: unexpected unarmed RO rescue', file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--preflight', action='store_true')
    mode.add_argument('--live-rw', action='store_true')
    mode.add_argument('--qualify-guard-ro', action='store_true')
    mode.add_argument('--rescue', action='store_true')
    args = parser.parse_args()
    if args.rescue:
        return rescue_only()
    if args.preflight:
        return inspect_only()
    return live_rw_test(read_only_qualification=args.qualify_guard_ro)


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as exc:
        print('LOADMASTER_RW_WATCHDOG_QUALIFICATION_HOLD: '
              + type(exc).__name__ + ': ' + str(exc), file=sys.stderr)
        sys.exit(2)
