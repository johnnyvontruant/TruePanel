"""No-remount integration tests for host-owned supervised write window."""
import unittest
from pathlib import Path
from unittest.mock import patch

from truepanel.cargo.backup_executor import BackupExecutionError
from truepanel.cargo.supervised_mount import SupervisedWriteWindow


class WriteWindowTests(unittest.TestCase):
    def setUp(self):
        self.commands = []
        self.mount = Path('/mnt/test-cartridge')
        self.by_id = '/dev/disk/by-id/usb-test_S3-0:0-part2'
        self.uuid = '6988-53EB'
        self.probe = patch('truepanel.cargo.supervised_mount.attest_cartridge_read_only')
        self.observed = self.probe.start()
        self.addCleanup(self.probe.stop)

    def runner(self, args):
        self.commands.append(args)

    def window(self, runner=None):
        return SupervisedWriteWindow(
            mount=self.mount, uuid=self.uuid, by_id=self.by_id,
            runner=runner or self.runner)

    def test_bounded_rw_restored_ro(self):
        with self.window():
            self.assertEqual(self.commands[0][-2:], ['remount,rw', str(self.mount)])
        self.assertEqual(self.commands[1][-2:], ['remount,ro', str(self.mount)])
        self.assertEqual(self.observed.call_count, 2)

    def test_raised_copy_error_restores_read_only(self):
        with self.assertRaisesRegex(ValueError, 'copy failed'):
            with self.window():
                raise ValueError('copy failed')
        self.assertEqual(self.commands[-1][-2], 'remount,ro')

    def test_mount_rw_failure_attempts_ro(self):
        def runner(args):
            self.runner(args)
            if 'remount,rw' in args:
                raise OSError('rw refused')
        with self.assertRaisesRegex(OSError, 'rw refused'):
            with self.window(runner=runner):
                self.fail('must not enter')
        self.assertEqual(self.commands[-1][-2], 'remount,ro')

    def test_failed_ro_restore_reported_as_critical(self):
        def runner(args):
            self.runner(args)
            if 'remount,ro' in args:
                raise OSError('restore failed')
        with self.assertRaisesRegex(BackupExecutionError, 'CRITICAL'):
            with self.window(runner=runner):
                pass

if __name__ == '__main__':
    unittest.main()
