"""Stdlib regression for the Mission Control read-only Loadmaster flight deck."""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from truepanel.cargo.flightdeck import KIND, read_flightdeck
from truepanel.cargo.provider import CachedCargoProvider


def sample():
    return {
        "schema_version": 1, "kind": KIND,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": "PREVIEW_ONLY", "read_only": True,
        "physical_authorized": False, "transfer_enabled": False,
        "cartridge": {"label": "Spare", "serial": "2532EA8D421A",
                      "uuid": "6ADA-80D5", "mount_mode": "ro"},
        "summary": {"export": 0, "ingest": 0, "verified": 2, "conflicts": 0},
        "actions": [
            {"direction": "NAS_TO_USB", "relative_path": "Outbound/episode.mkv",
             "size_bytes": 27, "sha256": "a" * 64, "status": "VERIFIED"},
            {"direction": "USB_TO_NAS", "relative_path": "Inbound/episode.mkv",
             "size_bytes": 82, "sha256": "b" * 64, "status": "VERIFIED"}],
        "receipts": {"backup": 1, "ingest": 1, "guard": "RESTORED_RO"},
    }


class FlightDeckTests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.TemporaryDirectory()
        self.addCleanup(self.root.cleanup)
        self.path = Path(self.root.name).resolve() / "flight.json"
        self.write(sample())

    def write(self, value):
        self.path.write_text(json.dumps(value))
        self.path.chmod(0o600)

    def test_valid_report(self):
        report = read_flightdeck(self.path)
        self.assertEqual(report["state"], "READY")
        self.assertEqual(report["summary"]["verified"], 2)
        self.assertEqual(report["receipts"]["guard"], "RESTORED_RO")
        self.assertFalse(report["physical_authorized"])
        self.assertFalse(report["transfer_enabled"])

    def test_missing_snapshot_is_disabled(self):
        self.assertEqual(read_flightdeck(None)["state"], "DISABLED")

    def test_missing_file_is_fail_closed(self):
        self.path.unlink()
        self.assertEqual(read_flightdeck(self.path)["state"], "INVALID")

    def test_expired_snapshot_is_invalid(self):
        payload = sample()
        payload["generated_at"] = (datetime.now(timezone.utc)-timedelta(days=3)).isoformat()
        self.write(payload)
        self.assertEqual(read_flightdeck(self.path)["state"], "INVALID")

    def test_future_timestamp_refused(self):
        payload = sample()
        payload["generated_at"] = (datetime.now(timezone.utc)+timedelta(days=1)).isoformat()
        self.write(payload)
        self.assertEqual(read_flightdeck(self.path)["state"], "INVALID")

    def test_report_cannot_grant_transfer_authority(self):
        for key, value in (("physical_authorized", True), ("transfer_enabled", True),
                           ("read_only", False), ("mode", "ARMED")):
            with self.subTest(key=key):
                payload = sample()
                payload[key] = value
                self.write(payload)
                self.assertEqual(read_flightdeck(self.path)["state"], "INVALID")

    def test_symlink_refused(self):
        link = self.path.parent / "linked.json"
        link.symlink_to(self.path)
        self.assertEqual(read_flightdeck(link)["state"], "INVALID")

    def test_public_mode_refused(self):
        self.path.chmod(0o644)
        self.assertEqual(read_flightdeck(self.path)["state"], "INVALID")

    def test_mismatched_summary_refused(self):
        payload = sample()
        payload["summary"]["export"] = 1
        self.write(payload)
        self.assertEqual(read_flightdeck(self.path)["state"], "INVALID")

    def test_path_traversal_refused(self):
        payload = sample()
        payload["actions"][0]["relative_path"] = "../outside"
        self.write(payload)
        self.assertEqual(read_flightdeck(self.path)["state"], "INVALID")

    def test_unmounted_cartridge_requires_review(self):
        payload = sample()
        payload["cartridge"]["mount_mode"] = "unmounted"
        self.write(payload)
        self.assertEqual(read_flightdeck(self.path)["state"], "REVIEW")

    def test_unbounded_report_refused(self):
        self.path.write_bytes(b" " * (128 * 1024 + 1))
        self.path.chmod(0o600)
        self.assertEqual(read_flightdeck(self.path)["state"], "INVALID")

    def test_existing_provider_includes_read_only_report(self):
        class Resolver:
            def snapshot(self):
                return {"groups": {"tv": [], "movies": []}, "state": "CLEAR"}
        provider = CachedCargoProvider(
            Resolver(), cache_seconds=0, loadmaster_enabled=True,
            cartridge_registry_path=None, loadmaster_flightdeck_path=self.path)
        result = provider.snapshot()
        self.assertEqual(result["loadmaster"]["flight_deck"]["state"], "READY")
        self.assertFalse(result["loadmaster"]["flight_deck"]["transfer_enabled"])


class PublisherEvidenceTests(unittest.TestCase):
    def setUp(self):
        from tools.loadmaster_spare_bidirectional_live_fire import ENTRIES
        self.root = tempfile.TemporaryDirectory()
        self.addCleanup(self.root.cleanup)
        root = Path(self.root.name).resolve()
        self.nas, self.usb, self.journal = (
            root / "nas", root / "usb", root / "journal")
        for folder in (self.nas, self.usb, self.journal):
            folder.mkdir()
        self.serial, self.uuid = "2532EA8D421A", "6ADA-80D5"
        for direction, relative in ENTRIES:
            for folder in (self.nas, self.usb):
                file = folder / relative
                file.parent.mkdir(parents=True, exist_ok=True)
                file.write_bytes(("acceptance:" + relative).encode("utf-8"))
        import hashlib
        export = ENTRIES[0][1]
        ingest = ENTRIES[1][1]
        self.export_hash = hashlib.sha256((self.nas / export).read_bytes()).hexdigest()
        self.ingest_hash = hashlib.sha256((self.usb / ingest).read_bytes()).hexdigest()
        (self.journal / "backup-manifest.json").write_text(json.dumps({
            "kind": "truepanel.cargo_backup_manifest",
            "items": [{"path": str(self.nas / export), "sha256": self.export_hash,
                       "size_bytes": (self.nas / export).stat().st_size}]}))
        (self.journal / "ingest.json").write_text(json.dumps({
            "kind": "truepanel.loadmaster.ingest_verified.v1",
            "direction": "USB_TO_NAS", "device_serial": self.serial,
            "cartridge_uuid": self.uuid, "relative_path": ingest,
            "sha256": self.ingest_hash,
            "size_bytes": (self.usb / ingest).stat().st_size}))
        (self.journal / "guard.json").write_text(json.dumps({"state": "RESTORED_RO"}))
        (self.journal / "approval.consumed").touch()

    def build(self):
        from tools.loadmaster_flightdeck_publish import build_snapshot
        return build_snapshot(nas=self.nas, usb=self.usb, journal=self.journal,
                              serial=self.serial, uuid=self.uuid)

    def test_both_directions_are_verified_from_files(self):
        report = self.build()
        self.assertEqual(report["summary"]["verified"], 2)
        self.assertFalse(report["physical_authorized"])
        self.assertEqual({a["direction"] for a in report["actions"]},
                         {"NAS_TO_USB", "USB_TO_NAS"})

    def test_tampered_destination_fails_closed(self):
        from tools.loadmaster_spare_bidirectional_live_fire import ENTRIES
        (self.nas / ENTRIES[1][1]).write_bytes(b"tampered")
        with self.assertRaises(ValueError):
            self.build()

    def test_missing_ingest_receipt_rejected(self):
        (self.journal / "ingest.json").unlink()
        with self.assertRaises(ValueError):
            self.build()

    def test_missing_consumed_approval_rejected(self):
        (self.journal / "approval.consumed").unlink()
        with self.assertRaises(ValueError):
            self.build()

    def test_missing_guard_receipt_rejected(self):
        (self.journal / "guard.json").unlink()
        with self.assertRaises(ValueError):
            self.build()


class RendererContracts(unittest.TestCase):
    def test_existing_loadmaster_drawer_contains_read_only_flightdeck(self):
        html = (Path(__file__).resolve().parents[1] /
                "truepanel/web/static/index.html").read_text()
        self.assertIn("function renderCargoFlightDeck(flightDeck,root)", html)
        self.assertIn("renderCargoFlightDeck(payload.flight_deck,root)", html)
        self.assertIn("PREVIEW ONLY", html)
        self.assertNotIn("onClickLoadmasterTransfer", html)


if __name__ == "__main__":
    unittest.main()
