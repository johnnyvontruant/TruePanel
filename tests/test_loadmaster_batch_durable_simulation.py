"""Durable callback-to-batch approval simulated integration tests."""
import tempfile
import unittest
from pathlib import Path

from truepanel.cargo.batch_authorization import BatchItem, batch_digest
from truepanel.cargo.batch_host_simulation import BatchSessionSpec
from truepanel.cargo.batch_durable_simulation import DurableSimulatedBatchHostSession
from truepanel.cargo.copy_button import CopyButtonConfirmation, LoadmasterCopyButtonGate
from truepanel.host.loadmaster_copy_button import LoadmasterCopyButtonService
from truepanel.host.loadmaster_session_bridge import LoadmasterHostSessionBridge
from truepanel.cargo.backup_executor import BackupExecutionError


class Reader:
    def read_level(self):
        return 1


class DurableBridgeTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.journal = Path(temp.name)
        self.t = 100.0
        items = tuple(BatchItem(f'Show {i}/ep.mkv', 200 + i, f'{i+1:064x}')
                      for i in range(3))
        self.spec = BatchSessionSpec('tv-n-z', '6988-53EB', '2532EA8D3DC7', items)
        self.digest = batch_digest(cartridge_id=self.spec.cartridge_id,
                                   cartridge_uuid=self.spec.cartridge_uuid, items=items)
        self.fresh = self.digest

    def setup_bridge(self):
        service = LoadmasterCopyButtonService(
            reader=Reader(),
            gate=LoadmasterCopyButtonGate(read_level=lambda: 1, clock=lambda: self.t))
        session = DurableSimulatedBatchHostSession(
            clock=lambda: self.t, fresh_digest=lambda: self.fresh,
            journal_root=self.journal)
        return LoadmasterHostSessionBridge(service=service, session=session), service

    def press(self, bridge, service):
        bridge.prepare_and_arm(self.spec)
        self.t += 1.0
        service.on_confirmation(CopyButtonConfirmation(
            cartridge_id=self.spec.cartridge_id,
            cartridge_uuid=self.spec.cartridge_uuid,
            device_serial=self.spec.device_serial,
            plan_digest=self.digest, confirmed_at_monotonic=self.t))
        return bridge.consume_read_only()

    def test_durable_consumption_then_replay_fails_new_bridge(self):
        bridge, service = self.setup_bridge()
        result = self.press(bridge, service)
        self.assertTrue(result['durably_consumed'])
        self.assertFalse(result['physical_execution_enabled'])
        self.assertEqual(len(list(self.journal.glob('*.consumed'))), 1)
        fresh, service2 = self.setup_bridge()
        with self.assertRaisesRegex(BackupExecutionError, 'already consumed'):
            self.press(fresh, service2)
        self.assertEqual(len(list(self.journal.glob('*.consumed'))), 1)

    def test_changed_intent_refuses_without_physical_execution(self):
        bridge, service = self.setup_bridge()
        bridge.prepare_and_arm(self.spec)
        self.t += 1.0
        service.on_confirmation(CopyButtonConfirmation(
            cartridge_id=self.spec.cartridge_id,
            cartridge_uuid=self.spec.cartridge_uuid,
            device_serial=self.spec.device_serial,
            plan_digest=self.digest, confirmed_at_monotonic=self.t))
        self.fresh = 'f' * 64
        with self.assertRaisesRegex(BackupExecutionError, 'changed'):
            bridge.consume_read_only()
        self.assertFalse(list(self.journal.glob('*.consumed')))


if __name__ == '__main__':
    unittest.main()
