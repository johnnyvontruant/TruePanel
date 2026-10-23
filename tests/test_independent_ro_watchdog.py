"""No mount operations: fake inspection/remount, fake systemd, tempfile-only state."""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from truepanel.cargo.backup_executor import BackupExecutionError
from truepanel.cargo import independent_ro_watchdog as guard


class FakeHardware:
    def __init__(self, mode='ro'):
        self.mode = mode
        self.calls = 0
        self.alive = True
        self.time = 1000.0
        self.reports = []
        self.mount_ro_calls = 0
        self.swapped = False
        self.fail_remount = False

    def clock(self):
        return self.time

    def sleep(self, sec):
        self.calls += 1
        self.time += sec

    def inspect(self, pin):
        if self.swapped:
            raise BackupExecutionError('cartridge identity changed')
        return self.mode

    def owner(self, pid, ticks):
        return self.alive

    def remount(self, mount):
        self.mount_ro_calls += 1
        if self.fail_remount:
            raise BackupExecutionError('CRITICAL: mount busy')
        self.mode = 'ro'

    def report(self, status):
        self.reports.append(status)

    def run(self, *, deadline=1010.0):
        return guard.guard_loop(pin=guard.SparePin(), owner_pid=500,
            owner_ticks=444, deadline=deadline, report=self.report,
            inspect=self.inspect, owner_alive=self.owner,
            remount_ro=self.remount, now=self.clock, pause=self.sleep)


class WatchdogSafetyTests(unittest.TestCase):
    def test_exact_spare_pin_required(self):
        with self.assertRaisesRegex(BackupExecutionError, 'exact spare'):
            guard._pinned(guard.SparePin(uuid='WRONG'))

    def test_identity_mount_read_only(self):
        def command(args):
            if args[0] == 'findmnt':
                return '/dev/sda2 /mnt/loadmaster-spare-ro exfat ro,nodev,noexec'
            if args[0] == 'blkid':
                return '6ADA-80D5' if 'UUID' in args else 'exfat'
            raise AssertionError(args)
        with patch.object(guard.os.path, 'realpath', side_effect=lambda p: '/dev/sda2'):
            self.assertEqual(guard.mount_mode(guard.SparePin(), command=command,
                             realpath=lambda p: '/dev/sda2'), 'ro')

    def test_identity_mount_read_write_reported(self):
        def command(args):
            if args[0] == 'findmnt':
                return '/dev/sda2 /mnt/loadmaster-spare-ro exfat rw,nodev,noexec'
            if args[0] == 'blkid':
                return '6ADA-80D5' if 'UUID' in args else 'exfat'
            raise AssertionError(args)
        self.assertEqual(guard.mount_mode(guard.SparePin(), command=command,
                                         realpath=lambda p: '/dev/sda2'), 'rw')

    def test_uuid_swap_refused(self):
        def command(args):
            if args[0] == 'findmnt':
                return '/dev/sda2 /mnt/loadmaster-spare-ro exfat rw,nodev'
            if args[0] == 'blkid':
                return 'WRONG' if 'UUID' in args else 'exfat'
            raise AssertionError(args)
        with self.assertRaisesRegex(BackupExecutionError, 'UUID'):
            guard.mount_mode(guard.SparePin(), command=command, realpath=lambda p: '/dev/sda2')

    def test_device_swap_refused(self):
        def command(args):
            if args[0] == 'findmnt':
                return '/dev/sda2 /mnt/loadmaster-spare-ro exfat rw,nodev'
            if args[0] == 'blkid':
                return '6ADA-80D5' if 'UUID' in args else 'exfat'
            raise AssertionError(args)
        with self.assertRaisesRegex(BackupExecutionError, 'pinned'):
            guard.mount_mode(guard.SparePin(), command=command,
                             realpath=lambda p: '/dev/sda2' if p == '/dev/sda2' else '/dev/sdb2')

    def test_ambiguous_mount_flags_refused(self):
        def command(args):
            if args[0] == 'findmnt':
                return '/dev/sda2 /mnt/loadmaster-spare-ro exfat rw,ro,nodev'
            if args[0] == 'blkid':
                return '6ADA-80D5' if 'UUID' in args else 'exfat'
            raise AssertionError(args)
        with self.assertRaisesRegex(BackupExecutionError, 'ambiguous'):
            guard.mount_mode(guard.SparePin(), command=command, realpath=lambda p: '/dev/sda2')

    def test_no_owner_at_start_never_arms(self):
        hw = FakeHardware()
        hw.alive = False
        with self.assertRaisesRegex(BackupExecutionError, 'owner exited'):
            hw.run()
        self.assertEqual(hw.reports, [])

    def test_owner_death_restores_ro(self):
        hw = FakeHardware()
        def sleep(dt):
            hw.mode = 'rw'
            hw.alive = False
            hw.time += dt
        hw.sleep = sleep
        self.assertEqual(hw.run(), 'RESTORED_RO')
        self.assertEqual(hw.mount_ro_calls, 1)
        self.assertEqual(hw.reports, ['READY', 'RESTORED_RO'])

    def test_deadline_restores_ro(self):
        hw = FakeHardware()
        def sleep(dt):
            hw.mode = 'rw'
            hw.time += dt
        hw.sleep = sleep
        self.assertEqual(hw.run(deadline=1000.2), 'RESTORED_RO')
        self.assertEqual(hw.mount_ro_calls, 1)

    def test_no_remount_when_already_ro(self):
        hw = FakeHardware()
        hw.run(deadline=1000.2)
        self.assertEqual(hw.mount_ro_calls, 0)

    def test_lease_duration_cannot_be_unbounded(self):
        with self.assertRaisesRegex(BackupExecutionError, 'lease'):
            FakeHardware().run(deadline=10_000.0)

    def test_swap_during_window_never_remounts_other_device(self):
        hw = FakeHardware()
        def sleep(dt):
            hw.mode = 'rw'
            hw.swapped = True
            hw.time += dt
        hw.sleep = sleep
        with self.assertRaisesRegex(BackupExecutionError, 'identity changed'):
            hw.run()
        self.assertEqual(hw.mount_ro_calls, 0)

    def test_failed_ro_restoration_never_claims_success(self):
        hw = FakeHardware()
        hw.fail_remount = True
        def sleep(dt):
            hw.mode = 'rw'
            hw.alive = False
            hw.time += dt
        hw.sleep = sleep
        with self.assertRaisesRegex(BackupExecutionError, 'CRITICAL'):
            hw.run()
        self.assertNotIn('RESTORED_RO', hw.reports)

    def test_fresh_heartbeat_required(self):
        hw = FakeHardware()
        hw.run(deadline=1004.0)
        self.assertGreater(hw.reports.count('READY'), 1)

    def _verify_status(self, *, status='READY', age=0.4, boot='boot-1',
                       unit_state='active', unit_pid=777, disk_guard_pid=777, same_namespace=True):
        with tempfile.TemporaryDirectory() as tmp:
            parent = Path(tmp)
            state = parent / 'guard.json'
            state.write_text(json.dumps({
                'state': status, 'unit': 'loadmaster-ro-guard-123456abcdef.service',
                'plan_digest': 'a' * 64, 'attempt_nonce': 'b' * 32,
                'owner_pid': 333, 'owner_ticks': 888,
                'guardian_pid': disk_guard_pid,
                'monotonic_at': 200.0 - age, 'boot_id': boot,
            }))
            state.chmod(0o600)
            parent.chmod(0o700)
            with patch.object(guard, '_status_file', return_value=None), \
                 patch.object(guard, '_owner_alive', return_value=True), \
                 patch.object(guard, 'same_host_mount_namespace', return_value=same_namespace):
                return guard.verify_independent_guard(path=state,
                    plan_digest='a'*64, attempt_nonce='b'*32, owner_pid=333, owner_ticks=888,
                    unit='loadmaster-ro-guard-123456abcdef.service',
                    monotonic_now=200.0, boot_id='boot-1',
                    systemd_show=lambda u: (unit_state, unit_pid))

    def test_active_separate_systemd_pid_required(self):
        self.assertTrue(self._verify_status())
        self.assertFalse(self._verify_status(unit_state='inactive'))
        self.assertFalse(self._verify_status(unit_pid=999))

    def test_namespace_guard_fails_closed(self):
        with patch.object(guard.os, 'readlink', side_effect=lambda path:
                          'mnt:[A]' if path == '/proc/1/ns/mnt' else 'mnt:[B]'):
            self.assertFalse(guard.same_host_mount_namespace(777))
        with patch.object(guard.os, 'readlink', side_effect=OSError):
            self.assertFalse(guard.same_host_mount_namespace(777))
        self.assertFalse(guard.same_host_mount_namespace(0))

    def test_guard_verifier_rejects_private_mount_namespace(self):
        self.assertFalse(self._verify_status(same_namespace=False))

    def test_stale_or_wrong_boot_guard_rejected(self):
        self.assertFalse(self._verify_status(age=4.0))
        self.assertFalse(self._verify_status(boot='wrong-boot'))
        self.assertFalse(self._verify_status(status='RESTORED_RO'))

    def test_status_writer_corrects_inherited_group_permissions(self):
        # Emulate a NAS dataset assigning 0770 despite open(..., 0600).
        # Do not make the verifier accept an unsafe status file.
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / 'guard.json'
            real_open = os.open

            def inherited_mode_open(path, flags, mode=0o777, *args, **kwargs):
                fd = real_open(path, flags, mode, *args, **kwargs)
                if str(path).endswith('.tmp'):
                    os.fchmod(fd, 0o770)
                return fd

            with patch.object(guard, '_status_file', return_value=None), \
                 patch.object(guard.os, 'open', side_effect=inherited_mode_open):
                for status in ('READY', 'READY', 'RESTORED_RO'):
                    guard.write_status(state, {'state': status})
                    self.assertEqual(state.stat().st_mode & 0o777, 0o600)
                    self.assertEqual(json.loads(state.read_text())['state'], status)

    def test_failed_private_mode_enforcement_refuses_publication(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / 'guard.json'
            with patch.object(guard, '_status_file', return_value=None), \
                 patch.object(guard.os, 'fchmod', side_effect=PermissionError('ACL denies chmod')):
                with self.assertRaises(PermissionError):
                    guard.write_status(state, {'state': 'READY'})
            self.assertFalse(state.exists())
            self.assertEqual(list(Path(tmp).iterdir()), [])

    def test_guard_writes_never_target_usb(self):
        with self.assertRaisesRegex(BackupExecutionError, 'private SSD'):
            guard._status_file(Path('/mnt/loadmaster-spare-ro/guard.json'))

    def test_owner_start_ticks_for_running_self(self):
        ticks = guard.owner_start_ticks(os.getpid())
        self.assertTrue(guard._owner_alive(os.getpid(), ticks))
        self.assertFalse(guard._owner_alive(os.getpid(), ticks + 1))


if __name__ == '__main__':
    unittest.main()


class GuardCLITests(unittest.TestCase):
    def test_preflight_does_not_mount_or_start_services(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location('test_guard_cli',
            Path(__file__).resolve().parents[1] / 'tools/loadmaster_spare_ro_guard.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with patch.object(module, 'host_ro_preflight', return_value={'state':'READ_ONLY'}), \
             patch.object(module, 'guard_loop') as loop, \
             patch.object(module, 'mount_mode') as mode:
            self.assertEqual(module.main(['--preflight']), 0)
            loop.assert_not_called()
            mode.assert_not_called()

    def test_bad_guard_launch_context_refuses_before_inspection(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location('test_guard_cli2',
            Path(__file__).resolve().parents[1] / 'tools/loadmaster_spare_ro_guard.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with patch.object(module.os, 'geteuid', return_value=0), \
             patch.object(module, 'mount_mode') as mode:
            with self.assertRaisesRegex(BackupExecutionError, 'incomplete'):
                module.main(['--watch', '--owner-pid', '50'])
            mode.assert_not_called()
