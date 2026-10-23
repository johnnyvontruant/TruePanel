"""Synthetic current-hash receipt and private Flight Deck publication tests."""
from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from truepanel.cargo.backup_executor import BackupExecutionError
from truepanel.cargo.flightdeck import read_flightdeck, KIND
from tools import loadmaster_tv_nz_production_flightdeck as flight


class TestProductionFlightDeck(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="loadmaster-live-evidence-")
        self.addCleanup(self.tmp.cleanup)
        self.state = Path(self.tmp.name).resolve()
        self.source = self.state / "source" / "Show" / "Episode.mkv"
        self.dest = self.state / "usb" / "Show" / "Episode.mkv"
        self.receipt = self.state / "receipts" / "manifest.json"
        for path in (self.source, self.dest, self.receipt):
            path.parent.mkdir(exist_ok=True, parents=True)
        self.payload = b"complete and checked episode" * 120
        self.digest = hashlib.sha256(self.payload).hexdigest()
        self.source.write_bytes(self.payload)
        self.dest.write_bytes(self.payload)
        self.receipt_payload = {
            "schema_version": 1, "kind": "truepanel.cargo_backup_manifest",
            "source": "loadmaster-verified-transaction",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "items": [{
                "path": str(self.source),
                "size_bytes": len(self.payload),
                "sha256": self.digest,
                "backed_up_at": datetime.now(timezone.utc).isoformat(),
            }],
        }
        self.save_receipt()

    def save_receipt(self):
        self.receipt.write_text(json.dumps(self.receipt_payload))

    def build(self):
        return flight.build_verified_copy_snapshot(
            source=self.source, destination=self.dest,
            manifest=self.receipt, relative_path="Show/Episode.mkv",
            size_bytes=len(self.payload), sha256=self.digest,
            serial="2532EA8D3DC7", uuid="6988-53EB",
            cartridge_label="TV N-Z")

    def test_valid_production_file_makes_readonly_snapshot(self):
        d = self.build()
        self.assertEqual(d["kind"], KIND)
        self.assertEqual(d["summary"]["verified"], 1)
        self.assertEqual(d["receipts"]["backup"], 1)
        self.assertEqual(d["receipts"]["guard"], "UNKNOWN")
        self.assertEqual(d["actions"][0]["status"], "VERIFIED")
        self.assertFalse(d["physical_authorized"])
        self.assertFalse(d["transfer_enabled"])

    def test_changed_usb_fails_with_no_success_report(self):
        self.dest.write_bytes(b"corrupt")
        with self.assertRaisesRegex(BackupExecutionError, "checksum"):
            self.build()

    def test_changed_source_fails(self):
        self.source.write_bytes(b"corrupt")
        with self.assertRaisesRegex(BackupExecutionError, "checksum"):
            self.build()

    def test_receipt_different_sha_fails(self):
        self.receipt_payload["items"][0]["sha256"] = "b" * 64
        self.save_receipt()
        with self.assertRaisesRegex(BackupExecutionError, "receipt"):
            self.build()

    def test_receipt_different_size_fails(self):
        self.receipt_payload["items"][0]["size_bytes"] = 1
        self.save_receipt()
        with self.assertRaisesRegex(BackupExecutionError, "receipt"):
            self.build()

    def test_receipt_missing_fails(self):
        self.receipt.unlink()
        with self.assertRaisesRegex(BackupExecutionError, "receipt"):
            self.build()

    def test_duplicate_receipt_path_fails(self):
        self.receipt_payload["items"].append(dict(self.receipt_payload["items"][0]))
        self.save_receipt()
        with self.assertRaisesRegex(BackupExecutionError, "uniquely"):
            self.build()

    def test_source_symlink_fails(self):
        actual = self.source.with_name("Actual.mkv")
        self.source.rename(actual)
        self.source.symlink_to(actual)
        with self.assertRaisesRegex(BackupExecutionError, "symlink"):
            self.build()

    def test_protected_daria_fails(self):
        with self.assertRaisesRegex(BackupExecutionError, "protected"):
            flight.build_verified_copy_snapshot(
                source=self.source, destination=self.dest,
                manifest=self.receipt, relative_path="Daria/S01E01.mkv",
                size_bytes=len(self.payload), sha256=self.digest,
                serial="2532EA8D3DC7", uuid="6988-53EB",
                cartridge_label="TV N-Z")

    def test_unsafe_relative_rejected(self):
        with self.assertRaisesRegex(BackupExecutionError, "contract"):
            flight.build_verified_copy_snapshot(
                source=self.source, destination=self.dest,
                manifest=self.receipt, relative_path="../S01.mkv",
                size_bytes=len(self.payload), sha256=self.digest,
                serial="2532EA8D3DC7", uuid="6988-53EB",
                cartridge_label="TV N-Z")

    def test_private_ssd_publication_validated(self):
        report = self.build()
        dest = self.state / "flightdeck-tv-nz-production.json"
        with patch.object(flight, "STATE", self.state), \
             patch.object(flight, "OUTPUT", dest), \
             patch.object(flight, "_root_only"):
            flight.publish_private_ssd(report, dest)
        self.assertEqual(dest.stat().st_mode & 0o777, 0o600)
        self.assertEqual(read_flightdeck(dest)["state"], "READY")

    def test_nonfixed_publication_path_rejected(self):
        report = self.build()
        with self.assertRaisesRegex(BackupExecutionError, "output path"):
            flight.publish_private_ssd(report, self.state / "other.json")


if __name__ == "__main__":
    unittest.main()
