"""Recovery-only never copies missing files or reuses spent authorization."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from truepanel.cargo.backup_executor import BackupExecutionError
from truepanel.cargo.batch_recovery_only import reconcile_sandbox_batch
from truepanel.cargo.batch_sandbox import execute_sandbox_batch


class RecoveryOnlyTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.nas = self.root/'nas'
        self.usb = self.root/'usb'
        self.nas.mkdir()
        self.usb.mkdir()
        self.manifest = self.root/'manifest.json'
        self.names = tuple(f'Show {i}/episode.mkv' for i in range(3))
        for i, name in enumerate(self.names):
            source = self.nas/name
            source.parent.mkdir()
            source.write_bytes(bytes([i+1]) * (2048+i))

    def recover(self):
        return reconcile_sandbox_batch(sandbox_root=self.root, nas=self.nas,
            usb=self.usb, manifest=self.manifest, names=self.names)

    def test_fully_missing_batch_requires_new_authorization(self):
        result = self.recover()
        self.assertEqual(result['new_copies'], 0)
        self.assertEqual(result['incomplete'], list(self.names))
        self.assertFalse(result['resumable_without_new_press'])
        self.assertFalse(self.manifest.exists())

    def test_partial_copy_only_reconciles_published_file(self):
        with self.assertRaises(InterruptedError):
            execute_sandbox_batch(sandbox_root=self.root, nas=self.nas,
                usb=self.usb, manifest=self.manifest, names=self.names,
                interrupt_after=1)
        first = self.usb/self.names[0]
        inode = first.stat().st_ino
        result = self.recover()
        self.assertEqual(len(result['reconciled']), 1)
        self.assertEqual(result['incomplete'], list(self.names[1:]))
        self.assertEqual(first.stat().st_ino, inode)
        self.assertFalse((self.usb/self.names[1]).exists())

    def test_published_before_manifest_reconciles_without_copy(self):
        source = self.nas/self.names[0]
        dest = self.usb/self.names[0]
        dest.parent.mkdir()
        dest.write_bytes(source.read_bytes())
        result = self.recover()
        self.assertEqual(result['reconciled'][0]['manifest_state'], 'EVIDENCE_RECORDED')
        self.assertEqual(len(json.loads(self.manifest.read_text())['items']), 1)
        self.assertFalse((self.usb/self.names[1]).exists())

    def test_corrupt_published_copy_blocks_manifest(self):
        dest = self.usb/self.names[0]
        dest.parent.mkdir()
        dest.write_bytes(b'corrupt')
        with self.assertRaisesRegex(BackupExecutionError, 'mismatch'):
            self.recover()
        self.assertFalse(self.manifest.exists())

    def test_recovery_never_invokes_copy_primitive(self):
        with patch('truepanel.cargo.backup_transaction.transfer_one_file',
                   side_effect=AssertionError('copy attempted')):
            self.assertEqual(self.recover()['new_copies'], 0)


if __name__ == '__main__':
    unittest.main()
