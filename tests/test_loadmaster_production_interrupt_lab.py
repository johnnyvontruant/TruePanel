"""Disposable-only interrupted-rsync qualification before bulk Loadmaster use.

No USB device, mount, GPIO or production media path is accessed. The test
creates a marker-bound temporary laboratory under /tmp and exercises both
transfer directions. Explicit newly supplied authorization is required after
an interruption. No automatic retries or final-file overwrites.
"""
from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path

from truepanel.cargo.resumable_rsync_lab import (
    InterruptedTransfer, LabError, plan, transfer,
)


class TestProductionInterruptionBoundaryLab(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(
            prefix="loadmaster-interrupt-lab-", dir="/tmp")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve(strict=True)
        (self.root / ".loadmaster-lab-only").write_text("LAB_ONLY\n")
        (self.root / "nas").mkdir()
        (self.root / "usb").mkdir()
        self.relative = "Synthetic Show/episode.mkv"

    def prepare(self, direction: str):
        source_root = (self.root / "nas" if direction == "NAS_TO_USB"
                       else self.root / "usb")
        target_root = (self.root / "usb" if direction == "NAS_TO_USB"
                       else self.root / "nas")
        source = source_root / self.relative
        destination = target_root / self.relative
        source.parent.mkdir()
        # 8 MiB deterministic synthetic data; bandwidth throttling ensures
        # the first rsync cannot finish before interruption is requested.
        content = b"loadmaster-disposable-fixture" * 300000
        source.write_bytes(content)
        return source, destination, hashlib.sha256(content).hexdigest()

    def exercise(self, direction: str):
        source, destination, digest = self.prepare(direction)
        intent = plan(self.root, direction=direction, relative=self.relative)
        self.assertEqual(intent.sha256, digest)
        with self.assertRaises(InterruptedTransfer):
            transfer(self.root, intent, transfer_approved=True,
                     interrupt_after=0.25, bwlimit_kib=128)
        self.assertFalse(destination.exists())
        with self.assertRaisesRegex(LabError, "fresh transfer approval"):
            transfer(self.root, intent, transfer_approved=False)
        self.assertFalse(destination.exists())
        finished = transfer(self.root, intent, transfer_approved=True)
        self.assertEqual(finished["state"], "NEW_VERIFIED_COPY")
        self.assertEqual(hashlib.sha256(destination.read_bytes()).hexdigest(), digest)
        self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), digest)
        # Idempotent verification cannot become a second write.
        again = transfer(self.root, intent, transfer_approved=False)
        self.assertEqual(again["state"], "PUBLISHED_ALREADY_VERIFIED")
        self.assertEqual(destination.read_bytes(), source.read_bytes())

    def test_export_interruption_requires_new_approval(self):
        self.exercise("NAS_TO_USB")

    def test_ingest_interruption_requires_new_approval(self):
        self.exercise("USB_TO_NAS")

    def test_conflicting_destination_never_overwritten(self):
        source, destination, _ = self.prepare("NAS_TO_USB")
        intent = plan(self.root, direction="NAS_TO_USB", relative=self.relative)
        destination.parent.mkdir()
        destination.write_bytes(b"preexisting user file")
        with self.assertRaisesRegex(LabError, "existing destination differs"):
            transfer(self.root, intent, transfer_approved=True)
        self.assertEqual(destination.read_bytes(), b"preexisting user file")
        self.assertTrue(source.exists())


if __name__ == "__main__":
    unittest.main()
