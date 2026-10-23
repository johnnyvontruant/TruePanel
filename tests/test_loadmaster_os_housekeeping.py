"""No-hardware regression for cross-platform Loadmaster OS housekeeping filter."""
from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path

from truepanel.cargo.backup_executor import BackupExecutionError
from truepanel.cargo.bidirectional_discovery import discover_bidirectional
from truepanel.cargo.bidirectional_host_scope import (
    CargoAction, CargoScope, inspect_bidirectional, validate_scope,
)
from truepanel.cargo.cartridges import CartridgeDefinition
from truepanel.cargo.loadmaster import (
    FileFingerprint, build_backlog_backup_plan, build_sync_plan,
    inventory_payload, scan_tree,
)
from truepanel.cargo.os_housekeeping import ignored_os_name, ignored_os_path
from truepanel.cargo.supervised_bidirectional_batch import transfer_one_approved


class NamesTest(unittest.TestCase):
    def test_macos_finder_resource_fork_and_search_database(self):
        names = (".DS_Store", "._movie.mkv", ".Spotlight-V100",
                 ".Trashes", ".fseventsd", ".AppleDouble", ".TemporaryItems",
                 ".DocumentRevisions-V100", ".localized", "__MACOSX",
                 ".VolumeIcon.icns", ".apdisk")
        for name in names:
            with self.subTest(name=name):
                self.assertTrue(ignored_os_name(name), name)

    def test_windows_housekeeping_and_case(self):
        names = ("Thumbs.db", "thumbS.DB", "ehthumbs.db", "desktop.ini",
                 "DESKTOP.INI", "System Volume Information", "$RECYCLE.BIN",
                 "Recycler", "thumbcache_1920.db", "iconcache_1024.DB")
        for name in names:
            with self.subTest(name=name):
                self.assertTrue(ignored_os_name(name), name)

    def test_keep_media_and_known_legitimate_dotfiles(self):
        for name in ("Film.mkv", "Episode.mp4", "poster.jpg",
                     "subtitles.srt", "movie.nfo", ".captions.srt",
                     ".movie.nfo", "Thumbs.mkv", "desktop.ini.mkv",
                     "my.desktop.ini.txt", ".hidden-video.mkv"):
            with self.subTest(name=name):
                self.assertFalse(ignored_os_name(name), name)

    def test_intermediate_directory_is_excluded(self):
        self.assertTrue(ignored_os_path("Season 1/.Trashes/file.mkv"))
        self.assertTrue(ignored_os_path("$Recycle.Bin/folder/other.mkv"))
        self.assertTrue(ignored_os_path("Series/._episode.mkv"))
        self.assertTrue(ignored_os_path("__MACOSX/Season/ep.mkv"))
        self.assertFalse(ignored_os_path("Series/.hidden-video.mkv"))

    def test_no_wholesale_hidden_exclusion(self):
        self.assertFalse(ignored_os_name(".my-private-notes.txt"))
        self.assertFalse(ignored_os_name("Windows Hidden Movie.mkv"))
        self.assertFalse(ignored_os_path("Subdir/.subtitle.srt"))


class IntegrationTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="loadmaster-os-filter-")
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name).resolve()
        self.nas, self.usb = self.base / "nas", self.base / "usb"
        self.nas.mkdir()
        self.usb.mkdir()
        self.cartridge = CartridgeDefinition(
            cartridge_id="test-media", label="Test", uuid="ABCD-1234",
            role="movies", source_prefix=self.nas,
            usb_relative_path=Path("Movies"), allow_ingest=True,
            allow_backup=True, delete_policy="never")
        (self.usb / "Movies").mkdir()
        self.usb_media = self.usb / "Movies"

    def put(self, root: Path, name: str, data: bytes = b"media") -> Path:
        dest = root / name
        dest.parent.mkdir(exist_ok=True, parents=True)
        dest.write_bytes(data)
        return dest

    def test_recursive_scan_ignores_os_artifacts_preserves_media(self):
        self.put(self.nas, "Series/S01E01.mkv")
        self.put(self.nas, "Series/.DS_Store", b"mac")
        self.put(self.nas, "Series/._S01E01.mkv", b"fork")
        self.put(self.nas, "Series/desktop.ini", b"win")
        self.put(self.nas, "Series/Thumbs.db", b"cache")
        self.put(self.nas, "System Volume Information/index.dat", b"index")
        self.put(self.nas, ".Spotlight-V100/store.db", b"index")
        self.put(self.nas, "Series/.hidden.nfo", b"notes")
        results = scan_tree(self.nas)
        self.assertEqual(set(results), {"Series/S01E01.mkv", "Series/.hidden.nfo"})
        self.assertTrue((self.nas / "Series/.DS_Store").exists())

    def test_usb_to_nas_only_media_is_planned(self):
        self.put(self.usb_media, "Movie/Film.mkv", b"film")
        self.put(self.usb_media, "Movie/._Film.mkv", b"fork")
        self.put(self.usb_media, "Movie/desktop.ini", b"ini")
        self.put(self.usb_media, "Movie/thumbcache_48.db", b"cache")
        self.put(self.usb_media, "$RECYCLE.BIN/metadata", b"bin")
        report = build_sync_plan(cartridge=self.cartridge, usb_mount=self.usb)
        self.assertEqual(report["summary"]["ingest_files"], 1)
        self.assertEqual([item["relative_path"] for item in report["actions"]],
                         ["Movie/Film.mkv"])
        self.assertEqual(report["state"], "READY")

    def test_nas_to_usb_and_stale_baseline_do_not_trigger_os_transfers(self):
        self.put(self.nas, "Series/Episode.mkv", b"episode")
        self.put(self.nas, "Series/.DS_Store", b"ignore")
        old = {"Series/Thumbs.db": FileFingerprint(100, 100)}
        report = build_sync_plan(cartridge=self.cartridge, usb_mount=self.usb,
                                 inventory=old)
        self.assertEqual(report["summary"]["backup_files"], 1)
        self.assertEqual([i["relative_path"] for i in report["actions"]],
                         ["Series/Episode.mkv"])
        self.assertFalse(report["conflicts"])

    def test_existing_inventory_export_is_filtered(self):
        self.put(self.nas, "Series/Episode.mkv")
        snap = inventory_payload(
            cartridge=self.cartridge,
            files={"Series/Episode.mkv": FileFingerprint(5, 100),
                   "Series/.DS_Store": FileFingerprint(3, 100)},
            captured_at="2026-10-23T21:00:00Z")
        self.assertEqual(set(snap["items"]), {"Series/Episode.mkv"})

    def test_backlog_ignores_os_artifacts_without_touching_sources(self):
        movie = self.put(self.nas, "Film/Movie.mkv", b"movie")
        mac = self.put(self.nas, "Film/._Movie.mkv", b"resourcefork")
        backlog = [{"current_path": str(path), "size_bytes": path.stat().st_size}
                   for path in (movie, mac)]
        report = build_backlog_backup_plan(
            cartridge=self.cartridge, usb_mount=self.usb, backlog_items=backlog)
        self.assertEqual([a["relative_path"] for a in report["actions"]],
                         ["Film/Movie.mkv"])
        self.assertTrue(mac.exists())

    def test_bidirectional_discovery_ignores_usb_and_nas_metadata(self):
        for root in (self.nas, self.usb_media):
            self.put(root, "Show/Episode.mkv", b"episode")
            self.put(root, "Show/._Episode.mkv", b"fork")
            self.put(root, "Show/Thumbs.db", b"cache")
            self.put(root, "System Volume Information/record", b"win")
            self.put(root, "$RECYCLE.BIN/record", b"bin")
        report = discover_bidirectional(
            nas_root=self.nas, usb_root=self.usb_media)
        self.assertEqual(report["counts"]["verified_match"], 1)
        self.assertEqual(len(report["items"]), 1)
        self.assertEqual(report["items"][0]["relative_path"], "Show/Episode.mkv")

    def test_host_inspection_denies_explicit_sidecar(self):
        self.put(self.usb_media, "Show/._Episode.mkv", b"fork")
        with self.assertRaisesRegex(BackupExecutionError, "housekeeping"):
            inspect_bidirectional(
                nas_root=self.nas, usb_root=self.usb_media,
                entries=(("USB_TO_NAS", "Show/._Episode.mkv"),))

    def test_scope_refuses_encoded_os_artifact(self):
        fake = CargoAction("USB_TO_NAS", "Show/Thumbs.db", 100, "a" * 64)
        scope = CargoScope("test-media", "ABCD-1234", "2532EA8D421A", (fake,))
        with self.assertRaisesRegex(BackupExecutionError, "housekeeping"):
            validate_scope(scope)

    def test_transfer_core_rejects_artifact_before_rsync(self):
        action = CargoAction("USB_TO_NAS", "Show/desktop.ini", 50, "a" * 64)
        with self.assertRaisesRegex(BackupExecutionError, "housekeeping"):
            transfer_one_approved(
                nas_root=self.nas, usb_root=self.usb_media,
                action=action, device_serial="2532EA8D421A")
        self.assertFalse((self.nas / "Show/desktop.ini").exists())


if __name__ == "__main__":
    unittest.main()
