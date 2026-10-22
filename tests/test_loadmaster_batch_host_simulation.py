"""Simulated host bridge callback tests, no GPIO and no USB."""
import unittest

from truepanel.cargo.batch_authorization import BatchItem, batch_digest
from truepanel.cargo.batch_host_simulation import BatchSessionSpec, SimulatedBatchHostSession
from truepanel.cargo.backup_executor import BackupExecutionError
from truepanel.cargo.copy_button import CopyButtonConfirmation, LoadmasterCopyButtonGate
from truepanel.host.loadmaster_copy_button import LoadmasterCopyButtonService
from truepanel.host.loadmaster_session_bridge import LoadmasterHostSessionBridge


class Reader:
    def read_level(self):
        return 1


class BatchBridgeTests(unittest.TestCase):
    def setUp(self):
        self.t = 100.
        self.items = tuple(BatchItem(f'Show {i}/ep.mkv', 100+i, f'{i+1:064x}') for i in range(3))
        self.spec = BatchSessionSpec('tv-n-z', '6988-53EB', '2532EA8D3DC7', self.items)
        self.digest = batch_digest(cartridge_id='tv-n-z', cartridge_uuid='6988-53EB', items=self.items)
        self.fresh = self.digest
        self.service = LoadmasterCopyButtonService(reader=Reader(),
            gate=LoadmasterCopyButtonGate(read_level=lambda: 1, clock=lambda: self.t))
        self.session = SimulatedBatchHostSession(clock=lambda: self.t,
            fresh_digest=lambda: self.fresh)
        self.bridge = LoadmasterHostSessionBridge(service=self.service, session=self.session)

    def confirmation(self, digest=None, at=101.):
        return CopyButtonConfirmation(
            cartridge_id='tv-n-z', cartridge_uuid='6988-53EB',
            device_serial='2532EA8D3DC7',
            plan_digest=self.digest if digest is None else digest,
            confirmed_at_monotonic=at)

    def test_three_file_host_bridge_single_use(self):
        response = self.bridge.prepare_and_arm(self.spec)
        self.assertEqual(response['backup_files'], 3)
        self.t = 102.
        self.service.on_confirmation(self.confirmation())
        result = self.bridge.consume_read_only()
        self.assertEqual(result['batch_items'], self.items)
        self.assertFalse(result['physical_execution_enabled'])
        with self.assertRaises(BackupExecutionError):
            self.bridge.consume_read_only()

    def test_changed_batch_refused_before_consumption(self):
        self.bridge.prepare_and_arm(self.spec)
        self.t = 102.
        self.service.on_confirmation(self.confirmation())
        self.fresh = 'f'*64
        with self.assertRaisesRegex(BackupExecutionError, 'mismatch'):
            self.bridge.consume_read_only()

    def test_wrong_digest_callback_refused(self):
        self.bridge.prepare_and_arm(self.spec)
        self.t = 102.
        with self.assertRaisesRegex(BackupExecutionError, 'scope mismatch'):
            self.service.on_confirmation(self.confirmation(digest='f'*64))

    def test_expired_callback_refused(self):
        self.bridge.prepare_and_arm(self.spec)
        self.t = 150.
        with self.assertRaisesRegex(BackupExecutionError, 'expired'):
            self.service.on_confirmation(self.confirmation())

    def test_unconfirmed_and_replay_refused(self):
        self.bridge.prepare_and_arm(self.spec)
        with self.assertRaises(BackupExecutionError):
            self.bridge.consume_read_only()
        self.bridge.disarm()
        with self.assertRaises(BackupExecutionError):
            self.service.on_confirmation(self.confirmation())

    def test_cannot_execute_physically(self):
        with self.assertRaisesRegex(BackupExecutionError, 'PHYSICAL_EXECUTION_DISABLED'):
            self.session.execute_physical()


if __name__ == '__main__':
    unittest.main()
