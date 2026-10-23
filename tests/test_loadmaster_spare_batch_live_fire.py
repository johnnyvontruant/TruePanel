"""CLI acceptance tests: spare-pinned runner defaults to read-only and fails closed."""
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from truepanel.cargo.backup_executor import BackupExecutionError
from tools.loadmaster_spare_batch_live_fire import execute, snapshot


class SpareBatchRunnerTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        self.nas = root / 'nas'
        self.nas.mkdir()
        self.usb = root / 'usb'
        self.usb.mkdir()
        self.names = ('Show1/episode.mkv', 'Show2/episode.mkv', 'Show3/episode.mkv')
        for i, name in enumerate(self.names):
            path = self.nas / name
            path.parent.mkdir()
            path.write_bytes(bytes([i+1]) * 1024)

    def test_inspection_does_not_mutate(self):
        items = snapshot(source_root=self.nas, usb_root=self.usb, names=self.names)
        self.assertEqual(len(items), 3)
        self.assertFalse(any(self.usb.rglob('*.mkv')))

    def test_existing_target_aborts(self):
        file = self.usb / self.names[1]
        file.parent.mkdir()
        file.write_bytes(b'existing')
        with self.assertRaisesRegex(BackupExecutionError, 'occupied'):
            snapshot(source_root=self.nas, usb_root=self.usb, names=self.names)
        self.assertEqual(file.read_bytes(), b'existing')

    def test_changed_source_hash_changes_batch_scope(self):
        before = snapshot(source_root=self.nas, usb_root=self.usb, names=self.names)
        (self.nas / self.names[0]).write_bytes(b'changed')
        after = snapshot(source_root=self.nas, usb_root=self.usb, names=self.names)
        self.assertNotEqual(before[0].sha256, after[0].sha256)

    def test_spare_identity_is_pinned_before_access(self):
        args = SimpleNamespace(mount=Path('/mnt/usb-tv-n-z'),
                               by_id='/dev/disk/by-id/something',
                               uuid='6988-53EB')
        with self.assertRaisesRegex(BackupExecutionError, 'verified spare'):
            execute(args)

    def test_unsafe_path_refused(self):
        for name in ('../escape', 'Show1/../../escape'):
            with self.assertRaises(BackupExecutionError):
                snapshot(source_root=self.nas, usb_root=self.usb, names=(name,))


if __name__ == '__main__':
    unittest.main()
