"""Crash-boundary and durable approval regressions. Disposable storage only."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from truepanel.cargo.backup_executor import BackupExecutionError, DurableConfirmationJournal
from truepanel.cargo.batch_sandbox import execute_sandbox_batch


class BatchBoundaryTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.nas, self.usb = self.root / 'nas', self.root / 'usb'
        self.nas.mkdir()
        self.usb.mkdir()
        self.manifest = self.root / 'manifest.json'
        self.names = tuple(f'Show {i}/episode.mkv' for i in range(1, 4))
        for i, relative in enumerate(self.names, 1):
            path = self.nas / relative
            path.parent.mkdir()
            path.write_bytes(bytes([i]) * (10000 + i))

    def run_batch(self, **overrides):
        return execute_sandbox_batch(sandbox_root=self.root, nas=self.nas,
            usb=self.usb, manifest=self.manifest, names=self.names, **overrides)

    def test_restart_after_every_manifest_boundary(self):
        for boundary in (1, 2, 3):
            with self.subTest(boundary=boundary):
                with tempfile.TemporaryDirectory() as temp:
                    root = Path(temp)
                    nas, usb = root / 'nas', root / 'usb'
                    nas.mkdir(); usb.mkdir()
                    for name in self.names:
                        src = nas / name
                        src.parent.mkdir()
                        src.write_bytes((self.nas / name).read_bytes())
                    manifest = root / 'manifest.json'
                    kwargs = dict(sandbox_root=root, nas=nas, usb=usb,
                                  manifest=manifest, names=self.names)
                    with self.assertRaises(InterruptedError):
                        execute_sandbox_batch(**kwargs, interrupt_after=boundary)
                    existing = {name: (usb / name).stat().st_ino
                                for name in self.names[:boundary]}
                    result = execute_sandbox_batch(**kwargs)
                    self.assertEqual(len(result['files']), 3)
                    for name, inode in existing.items():
                        self.assertEqual((usb / name).stat().st_ino, inode)
                    self.assertEqual(len(json.loads(manifest.read_text())['items']), 3)

    def test_publish_before_manifest_can_reconcile(self):
        from truepanel.cargo import batch_sandbox
        original = batch_sandbox.commit_verified_backup
        calls = [0]
        def fail_first(**kwargs):
            calls[0] += 1
            if calls[0] == 1:
                raise OSError('injected manifest failure after publish')
            return original(**kwargs)
        with patch.object(batch_sandbox, 'commit_verified_backup', side_effect=fail_first):
            with self.assertRaisesRegex(OSError, 'injected'):
                self.run_batch()
        first = self.usb / self.names[0]
        self.assertTrue(first.exists())
        inode = first.stat().st_ino
        self.assertFalse(self.manifest.exists())
        result = self.run_batch()
        self.assertEqual(result['files'][0]['copy_state'], 'RECOVERED_VERIFIED_COPY')
        self.assertEqual(first.stat().st_ino, inode)
        self.assertEqual(len(json.loads(self.manifest.read_text())['items']), 3)

    def test_durable_confirmation_replay_across_instances_refused(self):
        journal_root = self.root / 'journal'
        journal_root.mkdir(mode=0o700)
        kwargs = dict(cartridge_id='tv-n-z', plan_digest='a' * 64)
        DurableConfirmationJournal(journal_root).consume(**kwargs)
        with self.assertRaisesRegex(BackupExecutionError, 'already consumed'):
            DurableConfirmationJournal(journal_root).consume(**kwargs)
        self.assertEqual(len(list(journal_root.glob('*.consumed'))), 1)

    def test_existing_wrong_destination_refuses_entire_batch(self):
        dest = self.usb / self.names[2]
        dest.parent.mkdir()
        dest.write_bytes(b'wrong')
        with self.assertRaisesRegex(BackupExecutionError, 'mismatch'):
            self.run_batch()
        self.assertFalse((self.usb / self.names[0]).exists())
        self.assertEqual(dest.read_bytes(), b'wrong')


if __name__ == '__main__':
    unittest.main()
