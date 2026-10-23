"""Synthetic, no-hardware regression tests for exact TV N-Z HDD export scope."""
from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from truepanel.cargo.backup_executor import BackupExecutionError
from tools import loadmaster_tv_nz_hdd_export_scope as pilot


class TestReadOnlyHddExport(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="loadmaster-tv-nz-export-")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.library = self.root / "HDDs" / "Shows" / "TV N-Z"
        self.mount = self.root / "usb"
        self.usb = self.mount / "TV N-Z"
        self.relative = pilot.TV_NZ_TEST_RELATIVE
        self.source = self.library / self.relative
        self.dest = self.usb / self.relative
        self.source.parent.mkdir(parents=True)
        self.dest.parent.mkdir(parents=True)
        self.content = b"test data for one tv nz export" * 8
        self.source.write_bytes(self.content)
        self.reg = self.root / "cartridges.json"
        self.backlog = self.root / "backlog.json"
        self.config = {
            "schema_version": 1,
            "kind": "truepanel.loadmaster_cartridge_registry",
            "cartridges": [{
                "id": "tv-n-z",
                "label": "TV N-Z",
                "uuid": pilot.TV_NZ_UUID,
                "device_serial": pilot.TV_NZ_SERIAL,
                "role": "tv",
                "source_prefix": str(self.library),
                "usb_relative_path": "TV N-Z",
                "allow_backup": False,
                "allow_ingest": False,
                "delete_policy": "never",
            }],
        }
        self.save()
        self.patches = [
            patch.object(pilot, "TV_NZ_LIBRARY", self.library),
            patch.object(pilot, "TV_NZ_CARTRIDGE_ROOT", self.usb),
            patch.object(pilot, "TV_NZ_MOUNT", self.mount),
            patch.object(pilot, "EXPECTED_FILE", self.source),
            patch.object(pilot, "EXPECTED_DEST", self.dest),
            patch.object(pilot, "EXPECTED_BYTES", len(self.content)),
            patch.object(pilot, "EXPECTED_SHA256", hashlib.sha256(self.content).hexdigest()),
            patch.object(pilot, "mount_mode", return_value="ro"),
            patch.object(pilot, "attest_cartridge_read_only",
                         return_value=SimpleNamespace(matches_registry=True, read_only=True)),
        ]
        for item in self.patches:
            item.start()
            self.addCleanup(item.stop)

    def save(self):
        self.reg.write_text(json.dumps(self.config))
        self.backlog.write_text(json.dumps({
            "items": [{"current_path": str(self.source),
                       "size_bytes": len(self.content)}]}))

    def qualify(self):
        return pilot.qualify_read_only(registry=self.reg, backlog=self.backlog)

    def test_complete_one_way_scope_never_authorizes_write(self):
        result = self.qualify()
        self.assertEqual(result["state"], "TV_NZ_HDD_EXPORT_SCOPE_READ_ONLY_PASS")
        self.assertFalse(result["physical_authorized"])
        self.assertFalse(result["usb_written"])
        self.assertFalse(result["hdd_written"])
        self.assertFalse(result["gpio_armed"])
        self.assertEqual(result["direction"], "NAS_TO_USB")
        self.assertFalse(self.dest.exists())

    def test_destination_collision_rejected_before_hashing(self):
        self.dest.write_bytes(b"existing media")
        with self.assertRaisesRegex(BackupExecutionError, "occupied"):
            self.qualify()
        self.assertEqual(self.dest.read_bytes(), b"existing media")

    def test_modified_source_rejected(self):
        self.source.write_bytes(b"changed contents")
        with self.assertRaisesRegex(BackupExecutionError, "changed"):
            self.qualify()

    def test_same_size_changed_hash_rejected(self):
        self.source.write_bytes(b"X" * len(self.content))
        with self.assertRaisesRegex(BackupExecutionError, "checksum"):
            self.qualify()

    def test_symlinked_source_rejected(self):
        other = self.root / "different"
        other.write_bytes(self.content)
        self.source.unlink()
        self.source.symlink_to(other)
        with self.assertRaisesRegex(BackupExecutionError, "symlink"):
            self.qualify()

    def test_registry_uuid_swap_rejected(self):
        self.config["cartridges"][0]["uuid"] = "6ADA-80D5"
        self.save()
        with self.assertRaisesRegex(BackupExecutionError, "registration"):
            self.qualify()

    def test_registry_serial_swap_rejected(self):
        self.config["cartridges"][0]["device_serial"] = "2532EA8D421A"
        self.save()
        with self.assertRaisesRegex(BackupExecutionError, "registration"):
            self.qualify()

    def test_registry_permission_activation_rejected(self):
        self.config["cartridges"][0]["allow_backup"] = True
        self.save()
        with self.assertRaisesRegex(BackupExecutionError, "registration"):
            self.qualify()

    def test_usb_rw_mount_rejected(self):
        with patch.object(pilot, "mount_mode", return_value="rw"):
            with self.assertRaisesRegex(BackupExecutionError, "read-only"):
                self.qualify()

    def test_ledger_missing_rejected(self):
        self.backlog.write_text(json.dumps({"items": []}))
        with self.assertRaisesRegex(BackupExecutionError, "ledger"):
            self.qualify()

    def test_protected_daria_filename_rejected(self):
        with patch.object(pilot, "EXPECTED_FILE",
                          self.library / "Daria (1997)" / "S01E01.mkv"):
            with self.assertRaisesRegex(BackupExecutionError, "protected"):
                self.qualify()

    def test_housekeeping_exclusion(self):
        with patch.object(pilot, "TV_NZ_TEST_RELATIVE", "Show/._episode.mkv"):
            with self.assertRaisesRegex(BackupExecutionError, "protected"):
                self.qualify()

    def test_attestation_failure_rejected(self):
        with patch.object(pilot, "attest_cartridge_read_only",
                          return_value=SimpleNamespace(
                              matches_registry=False, read_only=True)):
            with self.assertRaisesRegex(BackupExecutionError, "attestation"):
                self.qualify()


if __name__ == "__main__":
    unittest.main()
