"""No-hardware tests for opt-in degraded-pool HDD pilot candidate inventory."""
from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from tools.loadmaster_hdd_pilot_candidates import select_hdd_candidates


class PilotReadinessTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="loadmaster-hdd-readiness-")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.library = self.root / "HDDs"
        self.library.mkdir()
        self.show = self.library / "Shows"
        self.movie = self.library / "Movies"
        self.show.mkdir()
        self.movie.mkdir()
        self.registry = self.root / "registry.json"
        self.backlog = self.root / "backlog.json"
        self.entries = []
        self.registry.write_text(json.dumps({
            "schema_version": 1,
            "kind": "truepanel.loadmaster_cartridge_registry",
            "cartridges": [
                {"id": "tv", "label": "TV backup", "uuid": "AABB-CCDD",
                 "role": "tv", "source_prefix": str(self.show),
                 "usb_relative_path": "TV", "allow_backup": True,
                 "delete_policy": "never"},
                {"id": "movies", "label": "Movie backup", "uuid": "EEFF-0123",
                 "role": "movies", "source_prefix": str(self.movie),
                 "usb_relative_path": "Movies", "allow_backup": True,
                 "delete_policy": "never"},
            ]}))
        self.update_ledger()

    def update_ledger(self):
        now = datetime.now(timezone.utc).isoformat()
        self.backlog.write_text(json.dumps({
            "schema_version": 1, "kind": "truepanel.loadmaster_backlog",
            "updated_at": now, "observe_after": now,
            "items": [
                {"current_path": str(p), "size_bytes": size,
                 "first_seen_at": now, "last_seen_at": now,
                 "required_after": now} for p, size in self.entries
            ],
        }))

    def add(self, root: Path, relative: str, content: bytes = b"test"):
        file = root / relative
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_bytes(content)
        self.entries.append((file, len(content)))
        self.update_ledger()
        return file

    def plan(self, *, health="DEGRADED"):
        return select_hdd_candidates(
            registry=self.registry, backlog=self.backlog,
            library_root=self.library, pool_health=health,
            max_bytes=100_000)

    def test_disabled_registry_backup_still_surveys_but_never_arms(self):
        self.add(self.show, "Regular Show/episode.mkv")
        data = json.loads(self.registry.read_text())
        data["cartridges"][0]["allow_backup"] = False
        self.registry.write_text(json.dumps(data))
        report = self.plan()
        self.assertEqual(report["eligible_total"], 1)
        self.assertFalse(report["candidates"][0]["backup_permission_enabled"])
        self.assertFalse(report["physical_authorized"])

    def test_degraded_pool_can_preview_without_write_authority(self):
        self.add(self.show, "Ordinary Show/episode.mkv", b"abcd")
        report = self.plan()
        self.assertEqual(report["state"], "HDD_PILOT_READ_ONLY_CANDIDATES")
        self.assertTrue(report["degraded_pool_risk"])
        self.assertFalse(report["hdd_written"])
        self.assertFalse(report["usb_written"])
        self.assertFalse(report["physical_authorized"])
        self.assertEqual(report["candidates"][0]["direction"], "NAS_TO_USB")

    def test_daria_never_appears_even_when_in_ledger(self):
        self.add(self.show, "Daria (1997)/S01E01.mkv")
        self.add(self.show, "Regular Show/S01E01.mkv")
        report = self.plan()
        self.assertEqual(report["counts"]["skipped_protected_media"], 1)
        self.assertEqual(report["eligible_total"], 1)
        self.assertNotIn("Daria", json.dumps(report["candidates"]))

    def test_os_metadata_excluded_and_original_preserved(self):
        metadata = self.add(self.show, "Regular Show/._episode.mkv")
        self.add(self.show, "Regular Show/episode.mkv")
        report = self.plan()
        self.assertEqual(report["counts"]["skipped_housekeeping"], 1)
        self.assertEqual(report["eligible_total"], 1)
        self.assertTrue(metadata.exists())

    def test_symlink_and_changed_size_excluded(self):
        self.add(self.show, "Regular Show/episode.mkv", b"data")
        missing = self.show / "Other/episode.mkv"
        self.entries.append((missing, 45))
        self.update_ledger()
        report = self.plan()
        self.assertEqual(report["counts"]["missing_or_changed"], 1)
        self.assertEqual(report["eligible_total"], 1)

    def test_symlink_file_excluded(self):
        real = self.add(self.show, "Real/episode.mkv", b"real")
        alias = self.show / "Alias/episode.mkv"
        alias.parent.mkdir()
        alias.symlink_to(real)
        self.entries.append((alias, 4))
        self.update_ledger()
        report = self.plan()
        self.assertEqual(report["counts"]["missing_or_changed"], 1)

    def test_nested_media_not_silently_selected(self):
        self.add(self.show, "Show/Season 1/episode.mkv")
        report = self.plan()
        self.assertEqual(report["counts"]["unsupported_depth"], 1)
        self.assertEqual(report["eligible_total"], 0)

    def test_oversized_media_not_selected(self):
        self.add(self.show, "Big Film/film.mkv", b"x" * 100_001)
        report = self.plan()
        self.assertEqual(report["counts"]["oversized"], 1)

    def test_select_three_smallest_candidates(self):
        for i, size in enumerate((7, 4, 6, 3, 5)):
            self.add(self.show, f"Show {i}/episode.mkv", b"X" * size)
        report = self.plan()
        self.assertEqual(report["eligible_total"], 5)
        self.assertEqual(len(report["candidates"]), 3)
        self.assertEqual([c["size_bytes"] for c in report["candidates"]], [3, 4, 5])

    def test_empty_ledger_is_not_an_authorized_transfer(self):
        report = self.plan(health="ONLINE")
        self.assertEqual(report["state"], "HDD_PILOT_NO_CANDIDATES")
        self.assertFalse(report["degraded_pool_risk"])
        self.assertFalse(report["physical_authorized"])
        self.assertEqual(report["candidates"], [])

    def test_outside_library_path_not_selected(self):
        self.add(self.show, "Regular Show/episode.mkv")
        outside = self.root / "outside.mkv"
        outside.write_bytes(b"data")
        self.entries.append((outside, 4))
        self.update_ledger()
        report = self.plan()
        self.assertEqual(report["counts"]["out_of_scope"], 1)


if __name__ == "__main__":
    unittest.main()
