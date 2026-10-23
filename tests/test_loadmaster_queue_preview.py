"""No-hardware tests for ledger-only, cartridge-aware Loadmaster queue previews."""
from __future__ import annotations

import unittest
from pathlib import Path

from truepanel.cargo.backlog import empty_backlog
from truepanel.cargo.cartridges import CartridgeDefinition
from truepanel.cargo.queue_preview import (
    preview_cartridge_queue, QueuePreviewError,
)


class TestQueuePreview(unittest.TestCase):
    def setUp(self):
        self.tv = CartridgeDefinition(
            cartridge_id="tv-n-z", label="TV N-Z", uuid="6988-53EB",
            role="tv", source_prefix=Path("/mnt/HDDs/Shows/TV N-Z"),
            usb_relative_path=Path("TV N-Z"),
            device_serial="2532EA8D3DC7",
            allow_ingest=False, allow_backup=False, delete_policy="never")
        self.movies = CartridgeDefinition(
            cartridge_id="movies", label="Movies", uuid="1234-ABCD",
            role="movies", source_prefix=Path("/mnt/HDDs/Movies"),
            usb_relative_path=Path("Movies"), allow_backup=True)
        self.backlog = empty_backlog()
        self.base = "2026-10-23T20:00:00+00:00"

    def add(self, path, size=5, required=None):
        self.backlog["items"].append({
            "current_path": str(path), "size_bytes": size,
            "title": "TV", "detail": "", "source": "sonarr",
            "source_imported_at": None,
            "first_seen_at": self.base,
            "last_seen_at": self.base,
            "required_after": required or self.base,
        })

    def preview(self, **kwargs):
        return preview_cartridge_queue(
            cartridges=[self.tv, self.movies], backlog=self.backlog,
            **kwargs)

    def test_empty_safe_preview(self):
        p = self.preview()
        self.assertFalse(p["physical_authorized"])
        self.assertFalse(p["media_scanned"])
        self.assertFalse(p["files_modified"])
        self.assertEqual(len(p["cartridges"]), 2)

    def test_deactivated_registry_remains_blocked(self):
        self.add("/mnt/HDDs/Shows/TV N-Z/Show/Episode.mkv", size=400)
        p = self.preview(cartridge_id="tv-n-z")
        self.assertEqual(p["cartridges"][0]["pending_items"], 1)
        self.assertEqual(p["cartridges"][0]["pending_bytes"], 400)
        self.assertEqual(p["cartridges"][0]["rows"][0]["state"], "REVIEW")
        self.assertEqual(p["cartridges"][0]["rows"][0]["reason"], "BACKUP_DISABLED")
        self.assertFalse(p["transfer_enabled"])

    def test_enabled_policy_still_requires_physical_verification(self):
        self.add("/mnt/HDDs/Movies/Film/Film.mkv")
        p = self.preview(cartridge_id="movies")
        self.assertEqual(p["cartridges"][0]["rows"][0]["reason"],
                         "NEEDS_SOURCE_AND_DEVICE_VERIFICATION")
        self.assertFalse(p["source_hashes_verified"])
        self.assertFalse(p["physical_authorized"])

    def test_excludes_daria_and_displays_no_daria_paths(self):
        self.add("/mnt/HDDs/Shows/TV N-Z/Daria (1997)/S01.mkv")
        self.add("/mnt/HDDs/Shows/TV N-Z/Other/Episode.mkv")
        p = self.preview(cartridge_id="tv-n-z")["cartridges"][0]
        self.assertEqual(p["excluded_protected"], 1)
        self.assertEqual(p["pending_items"], 1)
        self.assertNotIn("Daria", str(p["rows"]))

    def test_excludes_os_housekeeping_and_stage(self):
        self.add("/mnt/HDDs/Shows/TV N-Z/Show/._Episode.mkv")
        self.add("/mnt/HDDs/Shows/TV N-Z/.loadmaster-rsync-stage/a")
        p = self.preview(cartridge_id="tv-n-z")["cartridges"][0]
        self.assertEqual(p["excluded_housekeeping"], 2)
        self.assertEqual(p["pending_items"], 0)

    def test_nested_relative_paths_are_review_only_unsupported(self):
        self.add("/mnt/HDDs/Shows/TV N-Z/A/B/C.mkv")
        p = self.preview(cartridge_id="tv-n-z")["cartridges"][0]
        self.assertEqual(p["unsupported_paths"], 1)
        self.assertEqual(p["rows"], [])

    def test_unmapped_count_does_not_leak_source_path(self):
        self.add("/var/other/unmapped.mkv")
        p = self.preview()
        self.assertEqual(p["unmapped_entries"], 1)
        self.assertNotIn("/var/other", str(p))

    def test_overlapping_cartridges_choose_longest_prefix(self):
        nested = CartridgeDefinition(
            cartridge_id="special", label="Special", uuid="MOUNT-1",
            role="tv", source_prefix=self.tv.source_prefix / "Favorite",
            usb_relative_path=Path("Favorite"))
        self.add("/mnt/HDDs/Shows/TV N-Z/Favorite/Season/Ep.mkv")
        p = preview_cartridge_queue(
            cartridges=[self.tv, nested], backlog=self.backlog)
        by_id = {c["cartridge_id"]: c for c in p["cartridges"]}
        self.assertEqual(by_id["special"]["pending_items"], 1)
        self.assertEqual(by_id["tv-n-z"]["pending_items"], 0)

    def test_deterministic_oldest_first_and_row_limit(self):
        self.add("/mnt/HDDs/Shows/TV N-Z/New/Ep.mkv",
                 required="2026-10-23T23:00:00+00:00")
        self.add("/mnt/HDDs/Shows/TV N-Z/Old/Ep.mkv")
        p = self.preview(cartridge_id="tv-n-z", row_limit=1)["cartridges"][0]
        self.assertEqual(p["pending_items"], 2)
        self.assertEqual(len(p["rows"]), 1)
        self.assertIn("Old/Ep.mkv", p["rows"][0]["relative_path"])

    def test_row_limit_is_bounded(self):
        for count in (0, 11, -1, True, 1.5):
            with self.subTest(value=count):
                with self.assertRaises(QueuePreviewError):
                    self.preview(row_limit=count)

    def test_unknown_cartridge_is_rejected(self):
        with self.assertRaisesRegex(QueuePreviewError, "unknown"):
            self.preview(cartridge_id="does-not-exist")

    def test_malformed_backlog_refused(self):
        self.backlog["items"].append({"current_path": "relative"})
        with self.assertRaises(ValueError):
            self.preview()

    def test_source_still_not_inspected_even_when_path_absent(self):
        self.add("/mnt/HDDs/Shows/TV N-Z/Nonexistent/Episode.mkv")
        result = self.preview(cartridge_id="tv-n-z")
        self.assertEqual(result["cartridges"][0]["pending_items"], 1)
        self.assertFalse(result["source_hashes_verified"])
        self.assertFalse(result["usb_mount_checked"])


if __name__ == "__main__":
    unittest.main()
