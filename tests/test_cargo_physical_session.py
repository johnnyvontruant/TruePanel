"""No USB operations; trusted host session wiring tests."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from truepanel.cargo.backup_executor import BackupExecutionError
from truepanel.cargo.copy_button import CopyButtonConfirmation
from truepanel.cargo.physical_session import PhysicalSessionSpec, ReadOnlyHostSession


class HostSessionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.registry = self.root / 'registry.json'
        self.backlog = self.root / 'backlog.json'
        self.spec = PhysicalSessionSpec(
            registry=self.registry, backlog=self.backlog,
            cartridge_id='tv-n-z', mount=self.root / 'usb',
            by_id='/dev/disk/by-id/mock',
            source_path=self.root / 'nas' / 'VisionQuest (2026)' / '1x03.mkv',
            journal_root=self.root / 'journal',
        )
        self.spec.journal_root.mkdir()
        self.clock = 100.0
        self.session = ReadOnlyHostSession(clock=lambda: self.clock)
        self.card = type('Card', (), {
            'cartridge_id': 'tv-n-z', 'uuid': '6988-53EB',
            'device_serial': '2532EA8D3DC7',
        })()
        self.prepared = {
            'device_serial_registered': True,
            'plan_digest': 'a' * 64,
            'size_bytes': 533754539,
        }
        self.probe = patch('truepanel.cargo.physical_session.probe_one_episode',
                           return_value=self.prepared)
        self.load = patch('truepanel.cargo.cartridges.load_cartridge_registry',
                          return_value=[self.card])
        self.probe.start(); self.addCleanup(self.probe.stop)
        self.load.start(); self.addCleanup(self.load.stop)

    def confirmation(self, digest='a'*64):
        return CopyButtonConfirmation(
            cartridge_id='tv-n-z', cartridge_uuid='6988-53EB',
            device_serial='2532EA8D3DC7', plan_digest=digest,
            confirmed_at_monotonic=101.0,
        )

    def test_prepares_one_file_without_write(self):
        pf = self.session.prepare(self.spec)
        self.assertTrue(pf.ready)
        self.assertEqual(pf.backup_files, 1)
        self.assertEqual(pf.plan_digest, 'a'*64)

    def test_refuses_unconfirmed_session(self):
        self.session.prepare(self.spec)
        with self.assertRaises(BackupExecutionError):
            self.session.consume_after_physical_press()

    def test_confirmed_session_burns_digest(self):
        self.session.prepare(self.spec)
        self.clock = 102.0
        self.session.on_confirmation(self.confirmation())
        result = self.session.consume_after_physical_press()
        self.assertEqual(result['state'], 'HOST_APPROVAL_EVIDENCE_ONLY')
        self.assertFalse(result['executed'])
        self.assertEqual(len(list(self.spec.journal_root.iterdir())), 1)
        with self.assertRaises(BackupExecutionError):
            self.session.consume_after_physical_press()

    def test_changed_plan_is_rejected(self):
        self.session.prepare(self.spec)
        self.clock = 102.0
        self.session.on_confirmation(self.confirmation())
        self.prepared['plan_digest'] = 'b'*64
        with self.assertRaisesRegex(BackupExecutionError, 'intent changed'):
            self.session.consume_after_physical_press()

    def test_wrong_confirmation_is_rejected(self):
        self.session.prepare(self.spec)
        self.clock = 102.0
        self.session.on_confirmation(self.confirmation('b'*64))
        with self.assertRaises(BackupExecutionError):
            self.session.consume_after_physical_press()

    def test_serial_registration_required(self):
        self.prepared['device_serial_registered'] = False
        with self.assertRaisesRegex(BackupExecutionError, 'serial required'):
            self.session.prepare(self.spec)

    def test_physical_execution_fails_closed(self):
        with self.assertRaisesRegex(BackupExecutionError, 'PHYSICAL_EXECUTION_DISABLED'):
            self.session.execute_physical()

    def test_disarm_refuses_callback(self):
        self.session.prepare(self.spec)
        self.session.disarm()
        with self.assertRaises(BackupExecutionError):
            self.session.on_confirmation(self.confirmation())


if __name__ == '__main__':
    unittest.main()
