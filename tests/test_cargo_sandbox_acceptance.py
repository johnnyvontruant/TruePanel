import json
import tempfile
import unittest
from pathlib import Path

from truepanel.cargo.backup_executor import BackupExecutionError
from truepanel.cargo.sandbox_acceptance import run_sandbox_acceptance

class AcceptanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / '.loadmaster-disposable-sandbox').write_text('TEST-ONLY\n')
        self.nas = self.root / 'nas'
        self.usb = self.root / 'usb'
        self.nas.mkdir(); self.usb.mkdir()
        (self.nas / 'Show').mkdir()
        self.data = b'episode' * 200
        (self.nas / 'Show' / '1x03.mkv').write_bytes(self.data)
        self.plan = {'schema_version': 1, 'read_only': True, 'delete_policy': 'never',
                     'scope': 'durable_backlog', 'state': 'READY',
                     'cartridge': {'id':'sandbox'}, 'nas_root': str(self.nas),
                     'usb_root': str(self.usb),
                     'summary': {'scoped_items': 1, 'backup_files': 1,
                                 'backup_bytes': len(self.data), 'conflicts': 0, 'ingest_files': 0},
                     'actions': [{'direction':'NAS_TO_USB', 'relative_path':'Show/1x03.mkv',
                                  'size_bytes':len(self.data), 'reason':'NEW_ON_NAS'}],
                     'conflicts': []}
    def run_it(self, **kwargs):
        return run_sandbox_acceptance(plan=self.plan, sandbox_root=self.root, **kwargs)
    def test_end_to_end(self):
        result = self.run_it()
        self.assertEqual(result['manifest_state'], 'EVIDENCE_RECORDED')
        self.assertFalse(result['physical_transfer'])
        self.assertEqual(len(json.loads((self.root / 'manifest.json').read_text())['items']), 1)
    def test_interruption_and_recovery(self):
        with self.assertRaisesRegex(BackupExecutionError, 'INJECTED_AFTER_PUBLISH'):
            self.run_it(fault='after_publish')
        self.assertFalse((self.root / 'manifest.json').exists())
        self.assertEqual(self.run_it()['copy_state'], 'RECOVERED_PUBLISHED_COPY')
        self.assertEqual(self.run_it()['manifest_state'], 'ALREADY_RECORDED')
    def test_existing_copy_idempotent(self):
        self.run_it()
        before = (self.root / 'manifest.json').read_bytes()
        self.assertEqual(self.run_it()['manifest_state'], 'ALREADY_RECORDED')
        self.assertEqual(before, (self.root / 'manifest.json').read_bytes())
    def test_corrupt_recovery_refused(self):
        with self.assertRaisesRegex(BackupExecutionError, 'INJECTED_AFTER_PUBLISH'):
            self.run_it(fault='after_publish')
        (self.usb / 'Show' / '1x03.mkv').write_bytes(b'wrong')
        with self.assertRaisesRegex(BackupExecutionError, 'mismatch'):
            self.run_it()
        self.assertFalse((self.root / 'manifest.json').exists())
    def test_existing_content_not_overwritten(self):
        (self.usb / 'Show').mkdir()
        (self.usb / 'Show' / '1x03.mkv').write_bytes(b'important')
        with self.assertRaises(BackupExecutionError): self.run_it()
        self.assertEqual((self.usb / 'Show' / '1x03.mkv').read_bytes(), b'important')
    def test_escape_root_refused(self):
        self.plan['usb_root'] = str(self.root / 'elsewhere')
        with self.assertRaises(BackupExecutionError): self.run_it()
    def test_symlink_destination_refused(self):
        (self.usb / 'Show').symlink_to(self.nas / 'Show')
        with self.assertRaises(BackupExecutionError): self.run_it()
    def test_multiple_actions_refused(self):
        self.plan['actions'].append(self.plan['actions'][0].copy())
        with self.assertRaises(BackupExecutionError): self.run_it()

if __name__ == '__main__': unittest.main()
