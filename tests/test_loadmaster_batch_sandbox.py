"""Sandbox batch acceptance and interruption recovery."""
import json
import tempfile
import unittest
from pathlib import Path

from truepanel.cargo.backup_executor import BackupExecutionError
from truepanel.cargo.batch_sandbox import execute_sandbox_batch


class BatchSandboxTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.nas = self.root / "nas"
        self.usb = self.root / "usb"
        self.nas.mkdir()
        self.usb.mkdir()
        self.manifest = self.root / "manifest.json"
        self.names = [f"Show {i}/episode.mkv" for i in range(3)]
        for i, name in enumerate(self.names):
            path = self.nas / name
            path.parent.mkdir()
            path.write_bytes(bytes([i + 1]) * (4000 + i * 333))

    def execute(self, names=None, **kw):
        return execute_sandbox_batch(
            sandbox_root=self.root, nas=self.nas, usb=self.usb,
            manifest=self.manifest,
            names=self.names if names is None else names, **kw)

    def test_three_files_verified_and_recorded(self):
        result = self.execute()
        self.assertEqual(result["state"], "SANDBOX_BATCH_VERIFIED")
        self.assertEqual(len(result["files"]), 3)
        self.assertFalse(result["physical_authorized"])
        for name in self.names:
            self.assertEqual((self.nas / name).read_bytes(), (self.usb / name).read_bytes())
        self.assertEqual(len(json.loads(self.manifest.read_text())["items"]), 3)

    def test_restart_after_first_commit(self):
        with self.assertRaises(InterruptedError):
            self.execute(interrupt_after=1)
        original = (self.usb / self.names[0]).stat().st_ino
        result = self.execute()
        self.assertEqual(result["files"][0]["copy_state"], "RECOVERED_VERIFIED_COPY")
        self.assertEqual((self.usb / self.names[0]).stat().st_ino, original)
        self.assertEqual(len(json.loads(self.manifest.read_text())["items"]), 3)

    def test_preexisting_collision_never_overwritten(self):
        bad = self.usb / self.names[1]
        bad.parent.mkdir()
        bad.write_bytes(b"preexisting")
        with self.assertRaisesRegex(BackupExecutionError, "mismatch"):
            self.execute()
        self.assertEqual(bad.read_bytes(), b"preexisting")
        self.assertFalse((self.usb / self.names[0]).exists())

    def test_bad_source_prevents_all_writes(self):
        (self.nas / self.names[2]).unlink()
        with self.assertRaisesRegex(BackupExecutionError, "source"):
            self.execute()
        self.assertFalse(any(self.usb.rglob("*.mkv")))

    def test_corrupted_recovery_refused(self):
        with self.assertRaises(InterruptedError):
            self.execute(interrupt_after=1)
        (self.usb / self.names[0]).write_bytes(b"corrupt")
        with self.assertRaisesRegex(BackupExecutionError, "mismatch"):
            self.execute()
        self.assertFalse((self.usb / self.names[1]).exists())

    def test_reject_more_than_three_and_duplicate(self):
        with self.assertRaises(BackupExecutionError):
            self.execute(names=self.names + [self.names[0]])
        with self.assertRaises(BackupExecutionError):
            self.execute(names=self.names[:1] * 2)

    def test_reject_manifest_outside_root(self):
        with self.assertRaisesRegex(BackupExecutionError, "sandbox"):
            execute_sandbox_batch(
                sandbox_root=self.root, nas=self.nas, usb=self.usb,
                manifest=self.nas / "manifest.json", names=self.names)


if __name__ == "__main__":
    unittest.main()
