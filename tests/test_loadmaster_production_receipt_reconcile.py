"""Synthetic read-only matching of actual-backed-up pilot and pending ledger."""
from __future__ import annotations

import copy
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from truepanel.cargo.backlog import empty_backlog
from truepanel.cargo.production_receipt_reconcile import (
    ReceiptReconcileError, compare_verified_receipt,
)


class TestVerifiedReceiptReconciliation(unittest.TestCase):
    def setUp(self):
        self.source = Path("/mnt/HDDs/Shows/TV N-Z/Show/Episode.mkv")
        self.rel = "Show/Episode.mkv"
        self.digest = "a" * 64
        self.size = 400
        self.when = datetime(2026, 10, 23, 21, tzinfo=timezone.utc)
        self.backlog = empty_backlog(updated_at=self.when)
        self.row = {
            "current_path": str(self.source), "size_bytes": self.size,
            "first_seen_at": (self.when - timedelta(days=1)).isoformat(),
            "last_seen_at": self.when.isoformat(),
            "required_after": (self.when - timedelta(hours=1)).isoformat(),
            "title": "Show", "detail": "", "source": "sonarr",
            "source_imported_at": None,
        }
        self.backlog["items"] = [self.row]
        self.manifest = {
            "kind": "truepanel.cargo_backup_manifest",
            "items": [{
                "path": str(self.source), "size_bytes": self.size,
                "sha256": self.digest, "backed_up_at": self.when.isoformat(),
            }],
        }
        self.snapshot = {
            "mode": "PREVIEW_ONLY", "read_only": True,
            "physical_authorized": False, "transfer_enabled": False,
            "summary": {"verified": 1}, "receipts": {"backup": 1},
            "cartridge": {"mount_mode": "ro"},
            "actions": [{
                "direction": "NAS_TO_USB",
                "relative_path": self.rel,
                "size_bytes": self.size, "sha256": self.digest,
                "status": "VERIFIED",
            }],
        }

    def audit(self):
        return compare_verified_receipt(
            backlog=self.backlog, manifest=self.manifest,
            file_path=self.source, relative_path=self.rel,
            size_bytes=self.size, sha256=self.digest,
            independently_verified_snapshot=self.snapshot)

    def test_matching_authenticated_receipt_is_eligible_only(self):
        previous = copy.deepcopy(self.backlog)
        report = self.audit()
        self.assertEqual(report["pilot_status"], "VERIFIED_ELIGIBLE")
        self.assertEqual(report["eligible_for_future_reconciliation"], 1)
        self.assertEqual(report["pending_before"], 1)
        self.assertEqual(report["pending_after_hypothetical"], 0)
        self.assertFalse(report["ledger_mutated"])
        self.assertFalse(report["backlog_entry_removed"])
        self.assertEqual(previous, self.backlog)

    def test_no_backlog_entry_is_not_called_reconciled(self):
        self.backlog["items"] = []
        report = self.audit()
        self.assertEqual(report["pilot_status"], "NOT_CURRENTLY_QUEUED")
        self.assertEqual(report["eligible_for_future_reconciliation"], 0)
        self.assertEqual(report["pending_before"], 0)

    def test_stale_receipt_never_clears_entry(self):
        self.row["required_after"] = (self.when + timedelta(seconds=1)).isoformat()
        report = self.audit()
        self.assertEqual(report["pilot_status"], "STALE_RECEIPT_HOLD")
        self.assertEqual(report["pending_after_hypothetical"], 1)

    def test_size_mismatch_never_clears_entry(self):
        self.row["size_bytes"] = 401
        report = self.audit()
        self.assertEqual(report["pilot_status"], "SIZE_MISMATCH_HOLD")
        self.assertEqual(report["pending_after_hypothetical"], 1)

    def test_duplicate_receipt_rejected(self):
        self.manifest["items"].append(dict(self.manifest["items"][0]))
        with self.assertRaisesRegex(ReceiptReconcileError, "nonunique"):
            self.audit()

    def test_wrong_hash_rejected(self):
        self.manifest["items"][0]["sha256"] = "b" * 64
        with self.assertRaisesRegex(ReceiptReconcileError, "fingerprint"):
            self.audit()

    def test_bare_cached_report_does_not_count_without_verified_action(self):
        self.snapshot["actions"] = []
        with self.assertRaisesRegex(ReceiptReconcileError, "verification"):
            self.audit()

    def test_host_snapshot_claiming_authority_rejected(self):
        self.snapshot["physical_authorized"] = True
        with self.assertRaisesRegex(ReceiptReconcileError, "verification"):
            self.audit()

    def test_false_readonly_claim_rejected(self):
        self.snapshot["cartridge"]["mount_mode"] = "rw"
        with self.assertRaisesRegex(ReceiptReconcileError, "verification"):
            self.audit()

    def test_no_receipt_rejected(self):
        self.manifest["items"] = []
        with self.assertRaisesRegex(ReceiptReconcileError, "absent"):
            self.audit()

    def test_missing_timezone_rejected(self):
        self.manifest["items"][0]["backed_up_at"] = "2026-10-23T21:00:00"
        with self.assertRaisesRegex(ReceiptReconcileError, "timezone-less"):
            self.audit()

    def test_permanently_protected_daria_rejected(self):
        with self.assertRaisesRegex(ReceiptReconcileError, "protected"):
            compare_verified_receipt(
                backlog=self.backlog, manifest=self.manifest,
                file_path=Path("/mnt/HDDs/Shows/Daria/S01E01.mkv"),
                relative_path="Daria/S01E01.mkv",
                size_bytes=self.size, sha256=self.digest,
                independently_verified_snapshot=self.snapshot)

    def test_corrupt_pending_ledger_refused(self):
        self.row["current_path"] = "relative/bad"
        with self.assertRaises(Exception):
            self.audit()


if __name__ == "__main__":
    unittest.main()
