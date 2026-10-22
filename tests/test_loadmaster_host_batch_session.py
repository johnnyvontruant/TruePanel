"""Combined durable real host session + mount lifecycle tests; no real mounts."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from truepanel.cargo.batch_authorization import BatchItem, BatchApprovalScope
from truepanel.cargo.host_batch_session import HostBatchSpec, HostBatchApprovalSession
from truepanel.cargo.copy_button import CopyButtonConfirmation, LoadmasterCopyButtonGate
from truepanel.host.loadmaster_copy_button import LoadmasterCopyButtonService
from truepanel.host.loadmaster_session_bridge import LoadmasterHostSessionBridge
from truepanel.cargo.supervised_mount import SupervisedWriteWindow
from truepanel.cargo.backup_executor import BackupExecutionError


class Reader:
    def read_level(self):
        return 1


class HostBatchSessionIntegrationTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.journal = Path(tmp.name)
        self.time = 100.
        self.items = tuple(BatchItem(f'Show{i}/e.mkv', 10+i, f'{i+1:064x}') for i in range(3))
        self.scope = BatchApprovalScope(cartridge_id='tv-n-z', cartridge_uuid='6988-53EB', items=self.items)
        self.fresh = self.items
        self.spec = HostBatchSpec('tv-n-z','6988-53EB','2532EA8D3DC7',self.items,self.journal)

    def make_bridge(self):
        service = LoadmasterCopyButtonService(reader=Reader(),
            gate=LoadmasterCopyButtonGate(read_level=lambda: 1, clock=lambda: self.time))
        session = HostBatchApprovalSession(reattest=lambda: self.fresh,clock=lambda: self.time)
        return LoadmasterHostSessionBridge(service=service,session=session), service

    def press(self, bridge, service):
        bridge.prepare_and_arm(self.spec)
        self.time += 1
        service.on_confirmation(CopyButtonConfirmation(
            cartridge_id='tv-n-z',cartridge_uuid='6988-53EB',
            device_serial='2532EA8D3DC7',plan_digest=self.scope.digest,
            confirmed_at_monotonic=self.time))
        return bridge.consume_read_only()

    def test_durable_production_session_shape_and_replay(self):
        bridge, service = self.make_bridge()
        result = self.press(bridge,service)
        self.assertFalse(result['physical_execution_enabled'])
        self.assertEqual(result['plan_digest'],self.scope.digest)
        self.assertEqual(len(list(self.journal.glob('*.consumed'))),1)
        next_bridge, next_service = self.make_bridge()
        with self.assertRaisesRegex(BackupExecutionError,'already consumed'):
            self.press(next_bridge,next_service)

    def test_changed_batch_refused_without_journal_burn(self):
        bridge,service = self.make_bridge()
        bridge.prepare_and_arm(self.spec)
        self.time += 1
        service.on_confirmation(CopyButtonConfirmation(
            cartridge_id='tv-n-z',cartridge_uuid='6988-53EB',
            device_serial='2532EA8D3DC7',plan_digest=self.scope.digest,
            confirmed_at_monotonic=self.time))
        self.fresh = self.items[:2]
        with self.assertRaisesRegex(BackupExecutionError,'changed'):
            bridge.consume_read_only()
        self.assertFalse(list(self.journal.glob('*.consumed')))

    def test_mount_lifecycle_restores_after_copy_failure(self):
        commands = []
        with patch('truepanel.cargo.supervised_mount.attest_cartridge_read_only'):
            window = SupervisedWriteWindow(mount=Path('/mnt/disposable'),
                uuid='6988-53EB',by_id='/dev/disk/by-id/disposable',
                runner=lambda cmd: commands.append(cmd))
            with self.assertRaisesRegex(RuntimeError,'copy'):
                with window:
                    raise RuntimeError('copy interrupted')
        self.assertEqual([cmd[-2] for cmd in commands],['remount,rw','remount,ro'])

    def test_mount_restore_failure_is_critical(self):
        def runner(cmd):
            if cmd[-2] == 'remount,ro':
                raise OSError('simulated restore failure')
        with patch('truepanel.cargo.supervised_mount.attest_cartridge_read_only'):
            window = SupervisedWriteWindow(mount=Path('/mnt/disposable'),
                uuid='6988-53EB',by_id='/dev/disk/by-id/disposable',runner=runner)
            with self.assertRaisesRegex(BackupExecutionError,'CRITICAL'):
                with window:
                    pass


if __name__ == '__main__':
    unittest.main()
