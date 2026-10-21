"""End-to-end transaction tests use disposable directories only."""
import hashlib
import tempfile
import unittest
from pathlib import Path

from truepanel.cargo.backup_executor import BackupExecutionError
from truepanel.cargo.backup_transaction import transfer_one_file, verified_manifest_item


class TransactionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name)
        self.root = base
        self.nas = base / 'nas'
        self.usb = base / 'usb'
        self.nas.mkdir()
        self.usb.mkdir()
        (self.nas / 'VisionQuest (2026)').mkdir()
        self.relative = 'VisionQuest (2026)/1x03 - Reboot.mkv'
        self.data = b'VisionQuest episode test bytes' * 4000
        (self.nas / self.relative).write_bytes(self.data)

    def run_copy(self, **overrides):
        args = dict(source_root=self.nas, usb_root=self.usb,
                    relative_path=self.relative, expected_size=len(self.data),
                    sandbox_root=self.root)
        args.update(overrides)
        return transfer_one_file(**args)

    def test_verified_copy_and_evidence(self):
        result = self.run_copy()
        self.assertEqual(result['sha256'], hashlib.sha256(self.data).hexdigest())
        self.assertEqual((self.usb / self.relative).read_bytes(), self.data)
        evidence = verified_manifest_item(result)
        self.assertEqual(evidence['items'][0]['sha256'], result['sha256'])

    def test_existing_file_preserved(self):
        dest = self.usb / self.relative
        dest.parent.mkdir()
        dest.write_bytes(b'older')
        with self.assertRaisesRegex(BackupExecutionError, 'already exists'):
            self.run_copy()
        self.assertEqual(dest.read_bytes(), b'older')

    def test_changed_size(self):
        with self.assertRaisesRegex(BackupExecutionError, 'source changed'):
            self.run_copy(expected_size=13)
        self.assertFalse((self.usb / self.relative).exists())

    def test_rejects_non_sandbox_roots(self):
        with self.assertRaisesRegex(BackupExecutionError, 'outside sandbox'):
            self.run_copy(sandbox_root=self.nas)

    def test_rejects_unsafe_path(self):
        with self.assertRaisesRegex(BackupExecutionError, 'unsafe'):
            self.run_copy(relative_path='../outside')

    def test_rejects_source_symlink(self):
        p = self.nas / self.relative
        p.unlink()
        p.symlink_to('/etc/hosts')
        with self.assertRaises(OSError):
            self.run_copy()

    def test_rejects_destination_symlink(self):
        (self.usb / 'VisionQuest (2026)').symlink_to(self.nas)
        with self.assertRaises(OSError):
            self.run_copy()

    def test_interrupted_copy_never_published(self):
        with self.assertRaisesRegex(BackupExecutionError, 'interruption'):
            self.run_copy(fault='interrupt')
        self.assertFalse((self.usb / self.relative).exists())
        self.assertFalse(list(self.usb.rglob('.loadmaster-partial-*')))

    def test_corruption_never_published(self):
        with self.assertRaisesRegex(BackupExecutionError, 'checksum mismatch'):
            self.run_copy(fault='corrupt')
        self.assertFalse((self.usb / self.relative).exists())
        self.assertFalse(list(self.usb.rglob('.loadmaster-partial-*')))

    def test_collision_refused(self):
        with self.assertRaisesRegex(BackupExecutionError, 'publication refused'):
            self.run_copy(fault='collision')
        self.assertEqual((self.usb / self.relative).read_bytes(), b'existing file')
        self.assertFalse(list(self.usb.rglob('.loadmaster-partial-*')))

    def test_manifest_rejects_unverified(self):
        with self.assertRaisesRegex(BackupExecutionError, 'no verified'):
            verified_manifest_item({'state': 'READY'})


if __name__ == '__main__':
    unittest.main()
