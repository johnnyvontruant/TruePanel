"""Host-owned integration checks. No physical drives used."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from truepanel.cargo.backup_executor import BackupExecutionError
from truepanel.cargo.copy_button import CopyButtonConfirmation, LoadmasterCopyButtonGate
from truepanel.cargo.physical_session import PhysicalSessionSpec, ReadOnlyHostSession
from truepanel.host.loadmaster_copy_button import LoadmasterCopyButtonService
from truepanel.host.loadmaster_session_bridge import LoadmasterHostSessionBridge


class Reader:
    def read_level(self):
        return 1


class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.clock = 100.0
        self.spec = PhysicalSessionSpec(registry=root/'registry', backlog=root/'backlog',
            cartridge_id='tv-n-z', mount=root/'mount', by_id='/dev/disk/by-id/mock',
            source_path=root/'nas'/'VisionQuest (2026)'/'episode.mkv', journal_root=root/'journal')
        self.spec.journal_root.mkdir()
        self.ready = {'device_serial_registered': True, 'plan_digest': 'a'*64,
                      'size_bytes': 533754539}
        self.card = type('Card', (), {'cartridge_id':'tv-n-z', 'uuid':'6988-53EB',
                                     'device_serial':'2532EA8D3DC7'})()
        self.mockprobe = patch('truepanel.cargo.physical_session.probe_one_episode', return_value=self.ready)
        self.mockcards = patch('truepanel.cargo.cartridges.load_cartridge_registry', return_value=[self.card])
        self.mockprobe.start(); self.addCleanup(self.mockprobe.stop)
        self.mockcards.start(); self.addCleanup(self.mockcards.stop)
        self.service = LoadmasterCopyButtonService(reader=Reader(), gate=LoadmasterCopyButtonGate(read_level=lambda: 1, clock=lambda: self.clock))
        self.session = ReadOnlyHostSession(clock=lambda: self.clock)
        self.bridge = LoadmasterHostSessionBridge(service=self.service, session=self.session)

    def confirmation(self, digest='a'*64):
        return CopyButtonConfirmation(cartridge_id='tv-n-z', cartridge_uuid='6988-53EB',
            device_serial='2532EA8D3DC7', plan_digest=digest, confirmed_at_monotonic=101.)

    def test_arms_existing_host_gate(self):
        result = self.bridge.prepare_and_arm(self.spec)
        self.assertEqual(result['state'], 'HOST_ARMED_EVIDENCE_ONLY')
        self.assertTrue(self.service.snapshot()['armed'])
        self.assertFalse(result['executed'])

    def test_unconfirmed_refused(self):
        self.bridge.prepare_and_arm(self.spec)
        with self.assertRaisesRegex(BackupExecutionError, 'not received'):
            self.bridge.consume_read_only()

    def test_callback_to_durable_journal(self):
        self.bridge.prepare_and_arm(self.spec)
        self.clock = 102.0
        self.service.on_confirmation(self.confirmation())
        result = self.bridge.consume_read_only()
        self.assertEqual(result['state'], 'HOST_APPROVAL_EVIDENCE_ONLY')
        self.assertFalse(result['executed'])
        self.assertFalse(self.service.snapshot()['armed'])
        self.assertEqual(len(list(self.spec.journal_root.iterdir())), 1)
        with self.assertRaises(BackupExecutionError):
            self.bridge.consume_read_only()

    def test_changed_plan_refused(self):
        self.bridge.prepare_and_arm(self.spec)
        self.clock = 102.0
        self.service.on_confirmation(self.confirmation())
        self.ready['plan_digest'] = 'b'*64
        with self.assertRaisesRegex(BackupExecutionError, 'intent changed'):
            self.bridge.consume_read_only()
        self.assertFalse(self.service.snapshot()['armed'])

    def test_wrong_digest_refused(self):
        self.bridge.prepare_and_arm(self.spec)
        self.clock = 102.0
        self.service.on_confirmation(self.confirmation('b'*64))
        with self.assertRaises(BackupExecutionError):
            self.bridge.consume_read_only()

    def test_disarm_fails_closed(self):
        self.bridge.prepare_and_arm(self.spec)
        self.bridge.disarm()
        with self.assertRaises(BackupExecutionError):
            self.service.on_confirmation(self.confirmation())

    def test_double_arm_refused(self):
        self.bridge.prepare_and_arm(self.spec)
        with self.assertRaises(BackupExecutionError):
            self.bridge.prepare_and_arm(self.spec)

    def test_changed_callback_blocks_arm(self):
        self.service.on_confirmation = lambda _: None
        with self.assertRaisesRegex(BackupExecutionError, 'ownership lost'):
            self.bridge.prepare_and_arm(self.spec)
        self.assertFalse(self.service.snapshot()['armed'])

    def test_changed_callback_blocks_consumption_and_disarms(self):
        self.bridge.prepare_and_arm(self.spec)
        self.clock = 102.0
        self.service.on_confirmation(self.confirmation())
        self.service.on_confirmation = lambda _: None
        with self.assertRaisesRegex(BackupExecutionError, 'ownership lost'):
            self.bridge.consume_read_only()
        self.assertFalse(self.service.snapshot()['armed'])

    def test_physical_copy_stays_disabled(self):
        with self.assertRaisesRegex(BackupExecutionError, 'PHYSICAL_EXECUTION_DISABLED'):
            self.bridge.execute_physical()

    def test_rejects_service_with_other_callback(self):
        service = LoadmasterCopyButtonService(reader=Reader(), on_confirmation=lambda x: None)
        with self.assertRaisesRegex(BackupExecutionError, 'callback already assigned'):
            LoadmasterHostSessionBridge(service=service, session=self.session)


if __name__ == '__main__':
    unittest.main()
