"""Physical-readiness reporting is read-only and deliberately non-actuating."""
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from truepanel.cargo.physical_readiness import probe_one_episode
from truepanel.cargo.backup_executor import BackupExecutionError


class PhysicalReadinessTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / 'nas' / 'Show' / '1x03.mkv'
        self.source.parent.mkdir(parents=True)
        self.source.write_bytes(b'cargo')
        self.usb = self.root / 'usb'
        self.usb.mkdir()
        (self.usb / 'TV N-Z').mkdir()
        self.registry = self.root / 'registry.json'
        self.backlog = self.root / 'backlog.json'
        self.backlog.write_text(json.dumps({'items': [
            {'current_path': str(self.source), 'size_bytes': 5}]}))
        self.cartridge = SimpleNamespace(cartridge_id='tv-n-z',
            allow_ingest=False, allow_backup=False, delete_policy='never',
            uuid='6988-53EB', device_serial=None, source_prefix=self.root / 'nas',
            usb_relative_path=Path('TV N-Z'),
            public_dict=lambda: {'id': 'tv-n-z'})
        self.attestation = SimpleNamespace(matches_registry=True, read_only=True,
            uuid='6988-53EB', filesystem='exfat')
        self.plan = {'schema_version': 1, 'read_only': True,
            'delete_policy': 'never', 'state': 'READY', 'scope': 'durable_backlog',
            'conflicts': [], 'cartridge': {'id': 'tv-n-z'},
            'nas_root': str(self.root / 'nas'), 'usb_root': str(self.usb / 'TV N-Z'),
            'summary': {'scoped_items': 1, 'backup_files': 1, 'backup_bytes': 5,
                        'conflicts': 0, 'ingest_files': 0},
            'actions': [{'direction': 'NAS_TO_USB', 'relative_path': 'Show/1x03.mkv',
                         'size_bytes': 5, 'reason': 'NEW_ON_NAS'}]}
        self.patchers = [
            patch('truepanel.cargo.physical_readiness.load_cartridge_registry', return_value=[self.cartridge]),
            patch('truepanel.cargo.physical_readiness.attest_cartridge_read_only', return_value=self.attestation),
            patch('truepanel.cargo.physical_readiness.build_backlog_backup_plan', return_value=self.plan),
        ]
        for obj in self.patchers:
            obj.start()
            self.addCleanup(obj.stop)

    def probe(self):
        return probe_one_episode(registry=self.registry, backlog=self.backlog,
              cartridge_id='tv-n-z', mount=self.usb,
              by_id='/dev/disk/by-id/test-part2', source_path=self.source)

    def test_reports_missing_serial_and_stays_non_actuating(self):
        answer = self.probe()
        self.assertEqual(answer['state'], 'READ_ONLY_PREPARED')
        self.assertFalse(answer['executed'])
        self.assertFalse(answer['backup_authorized'])
        self.assertIn('REGISTER_TRUSTED_DEVICE_SERIAL', answer['remaining_gates'])
        self.assertFalse((self.usb / 'TV N-Z' / 'Show').exists())

    def test_serial_only_removes_serial_blocker(self):
        self.cartridge.device_serial = 'trusted-device-serial'
        answer = self.probe()
        self.assertNotIn('REGISTER_TRUSTED_DEVICE_SERIAL', answer['remaining_gates'])
        self.assertIn('LIVE_WRITABLE_MOUNT_ATTESTATION', answer['remaining_gates'])

    def test_rejects_backup_enabled(self):
        self.cartridge.allow_backup = True
        with self.assertRaisesRegex(BackupExecutionError, 'permission'):
            self.probe()

    def test_rejects_wrong_cartridge(self):
        with self.assertRaisesRegex(BackupExecutionError, 'uniquely'):
            probe_one_episode(registry=self.registry, backlog=self.backlog,
              cartridge_id='other', mount=self.usb,
              by_id='/dev/disk/by-id/test-part2', source_path=self.source)

    def test_rejects_duplicate_backlog_entry(self):
        item = {'current_path': str(self.source), 'size_bytes': 5}
        self.backlog.write_text(json.dumps({'items': [item, item]}))
        with self.assertRaisesRegex(BackupExecutionError, 'not unique'):
            self.probe()

    def test_rejects_nonready_plan(self):
        self.plan['state'] = 'HOLD'
        with self.assertRaises(BackupExecutionError):
            self.probe()


if __name__ == '__main__':
    unittest.main()
