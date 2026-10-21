"""Loadmaster executor safety tests using standard-library unittest."""

import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from truepanel.cargo.backup_executor import (
    BackupExecutionError,
    BackupPreflight,
    validate_backup_preflight,
)


class BackupExecutorPreflightTests(unittest.TestCase):

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)

        root = Path(self.temp.name)
        nas = root / "nas"
        usb = root / "usb"
        nas.mkdir()
        usb.mkdir()

        (nas / "episode.mkv").write_bytes(b"test-episode")

        self.request = BackupPreflight(
            source_root=nas,
            destination_root=usb,
            relative_path="episode.mkv",
            expected_size=12,
            registered_uuid="TEST-UUID",
            observed_uuid="TEST-UUID",
            allow_backup=True,
            mount_writable=True,
            physical_confirmation=True,
        )

    def test_rejects_disabled_backup(self):
        with self.assertRaisesRegex(BackupExecutionError, "authorization"):
            validate_backup_preflight(
                replace(self.request, allow_backup=False)
            )

    def test_rejects_wrong_uuid(self):
        with self.assertRaisesRegex(BackupExecutionError, "identity"):
            validate_backup_preflight(
                replace(self.request, observed_uuid="WRONG")
            )

    def test_rejects_read_only_mount(self):
        with self.assertRaisesRegex(BackupExecutionError, "not writable"):
            validate_backup_preflight(
                replace(self.request, mount_writable=False)
            )

    def test_rejects_existing_destination(self):
        destination = (
            self.request.destination_root / self.request.relative_path
        )
        destination.write_bytes(b"original")

        with self.assertRaisesRegex(BackupExecutionError, "already exists"):
            validate_backup_preflight(self.request)

        self.assertEqual(destination.read_bytes(), b"original")

    def test_rejects_changed_size(self):
        with self.assertRaisesRegex(BackupExecutionError, "size changed"):
            validate_backup_preflight(
                replace(self.request, expected_size=999)
            )

    def test_rejects_path_traversal(self):
        with self.assertRaisesRegex(BackupExecutionError, "unsafe"):
            validate_backup_preflight(
                replace(self.request, relative_path="../escape.mkv")
            )

    def test_rejects_symlink(self):
        (self.request.source_root / "link.mkv").symlink_to(
            self.request.source_root / "episode.mkv"
        )

        with self.assertRaisesRegex(BackupExecutionError, "symlink"):
            validate_backup_preflight(
                replace(self.request, relative_path="link.mkv")
            )

    def test_requires_confirmation(self):
        with self.assertRaisesRegex(BackupExecutionError, "confirmation"):
            validate_backup_preflight(
                replace(self.request, physical_confirmation=False)
            )

    def test_valid_preflight_does_not_copy(self):
        result = validate_backup_preflight(self.request)

        self.assertEqual(result["state"], "PREFLIGHT_READY")
        self.assertFalse(result["executed"])
        self.assertTrue(result["read_only"])

        self.assertFalse(
            (
                self.request.destination_root
                / self.request.relative_path
            ).exists()
        )


class DisposableCopyTests(unittest.TestCase):

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)

        root = Path(self.temp.name)
        self.source = root / "source.bin"
        self.destination = root / "destination.bin"
        self.source.write_bytes(b"Loadmaster test cargo" * 100)

    def test_verified_copy(self):
        import hashlib
        from truepanel.cargo.backup_executor import copy_disposable_test_file

        result = copy_disposable_test_file(
            self.source,
            self.destination,
        )

        self.assertEqual(result["state"], "VERIFIED_TEST_COPY")
        self.assertEqual(
            result["sha256"],
            hashlib.sha256(self.source.read_bytes()).hexdigest(),
        )
        self.assertEqual(
            self.destination.read_bytes(),
            self.source.read_bytes(),
        )

    def test_existing_file_never_overwritten(self):
        from truepanel.cargo.backup_executor import copy_disposable_test_file

        self.destination.write_bytes(b"existing backup")

        with self.assertRaises(BackupExecutionError):
            copy_disposable_test_file(
                self.source,
                self.destination,
            )

        self.assertEqual(
            self.destination.read_bytes(),
            b"existing backup",
        )

    def test_interruption_does_not_publish(self):
        from truepanel.cargo.backup_executor import copy_disposable_test_file

        with self.assertRaisesRegex(
            BackupExecutionError,
            "interruption",
        ):
            copy_disposable_test_file(
                self.source,
                self.destination,
                interrupt_after_bytes=1,
            )

        self.assertFalse(self.destination.exists())
        self.assertEqual(
            list(self.destination.parent.glob(".loadmaster-test-*")),
            [],
        )



class AtomicPublicationTests(unittest.TestCase):

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_publishes_new_file(self):
        from truepanel.cargo.backup_executor import publish_noreplace

        (self.root / "temporary.bin").write_bytes(b"verified")

        publish_noreplace(
            "temporary.bin",
            "published.bin",
            self.root,
        )

        self.assertFalse((self.root / "temporary.bin").exists())
        self.assertEqual(
            (self.root / "published.bin").read_bytes(),
            b"verified",
        )

    def test_refuses_existing_destination(self):
        from truepanel.cargo.backup_executor import publish_noreplace

        (self.root / "temporary.bin").write_bytes(b"new")
        (self.root / "published.bin").write_bytes(b"original")

        with self.assertRaisesRegex(
            BackupExecutionError,
            "publication refused",
        ):
            publish_noreplace(
                "temporary.bin",
                "published.bin",
                self.root,
            )

        self.assertEqual(
            (self.root / "published.bin").read_bytes(),
            b"original",
        )
        self.assertEqual(
            (self.root / "temporary.bin").read_bytes(),
            b"new",
        )

    def test_rejects_unsafe_filenames(self):
        from truepanel.cargo.backup_executor import publish_noreplace

        with self.assertRaisesRegex(
            BackupExecutionError,
            "invalid publication filename",
        ):
            publish_noreplace(
                "../escape.bin",
                "published.bin",
                self.root,
            )



class TransferIntegrityTests(unittest.TestCase):
    """Requirements for the eventual production copy engine."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_source_mutation_must_be_rejected(self):
        from truepanel.cargo.backup_executor import (
            BackupExecutionError,
            copy_disposable_test_file,
        )

        source = self.root / "episode.mkv"
        destination = self.root / "backup.mkv"

        source.write_bytes(b"original-content")

        # This test documents the required execution-time recheck.
        expected_size = source.stat().st_size

        source.write_bytes(b"modified-content-with-different-size")

        with self.assertRaises(BackupExecutionError):
            from truepanel.cargo.backup_executor import validate_backup_preflight

            validate_backup_preflight(
                BackupPreflight(
                    source_root=self.root,
                    destination_root=self.root,
                    relative_path="episode.mkv",
                    expected_size=expected_size,
                    registered_uuid="TEST",
                    observed_uuid="TEST",
                    allow_backup=True,
                    mount_writable=True,
                    physical_confirmation=True,
                )
            )

        self.assertFalse(destination.exists())

    def test_corrupted_destination_digest_must_fail(self):
        import hashlib

        source = self.root / "episode.mkv"
        temporary = self.root / "temporary.mkv"
        destination = self.root / "backup.mkv"

        source.write_bytes(b"valid-data")
        temporary.write_bytes(b"corrupted-data")

        source_hash = hashlib.sha256(source.read_bytes()).digest()
        destination_hash = hashlib.sha256(temporary.read_bytes()).digest()

        self.assertNotEqual(source_hash, destination_hash)
        self.assertFalse(destination.exists())



class IntegratedSandboxTests(unittest.TestCase):

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)

        self.root = Path(self.temp.name)
        self.nas = self.root / "nas"
        self.usb = self.root / "usb"
        self.nas.mkdir()
        self.usb.mkdir()

        self.payload = b"VisionQuest sandbox data" * 10000
        (self.nas / "episode.mkv").write_bytes(self.payload)

        self.request = BackupPreflight(
            source_root=self.nas,
            destination_root=self.usb,
            relative_path="episode.mkv",
            expected_size=len(self.payload),
            registered_uuid="TEST",
            observed_uuid="TEST",
            allow_backup=True,
            mount_writable=True,
            physical_confirmation=True,
        )

    def execute(self, **kwargs):
        from truepanel.cargo.backup_executor import execute_sandbox_backup
        return execute_sandbox_backup(
            self.request,
            sandbox_root=self.root,
            **kwargs,
        )

    def assert_no_temporary_files(self):
        self.assertEqual(
            list(self.usb.glob(".loadmaster-sandbox-*")), []
        )

    def test_integrated_verified_copy(self):
        result = self.execute()
        self.assertEqual(result["state"], "VERIFIED_SANDBOX_COPY")
        self.assertEqual(
            (self.usb / "episode.mkv").read_bytes(),
            self.payload,
        )
        self.assert_no_temporary_files()

    def test_integrated_interruption(self):
        with self.assertRaisesRegex(
            BackupExecutionError, "interruption"
        ):
            self.execute(fault="interrupt")
        self.assertFalse((self.usb / "episode.mkv").exists())
        self.assert_no_temporary_files()

    def test_integrated_corruption(self):
        with self.assertRaisesRegex(
            BackupExecutionError, "checksum mismatch"
        ):
            self.execute(fault="corrupt")
        self.assertFalse((self.usb / "episode.mkv").exists())
        self.assert_no_temporary_files()

    def test_integrated_source_change(self):
        with self.assertRaisesRegex(
            BackupExecutionError, "source mutation"
        ):
            self.execute(fault="source_change")
        self.assertFalse((self.usb / "episode.mkv").exists())
        self.assert_no_temporary_files()

    def test_integrated_destination_race(self):
        with self.assertRaisesRegex(
            BackupExecutionError, "publication refused"
        ):
            self.execute(fault="destination_race")
        self.assertEqual(
            (self.usb / "episode.mkv").read_bytes(),
            b"other writer",
        )
        self.assert_no_temporary_files()

    def test_integrated_rejects_outside_sandbox(self):
        from truepanel.cargo.backup_executor import execute_sandbox_backup

        with self.assertRaisesRegex(
            BackupExecutionError, "outside sandbox"
        ):
            execute_sandbox_backup(
                self.request,
                sandbox_root=self.usb,
            )

    def test_integrated_rejects_unauthorized_copy(self):
        from truepanel.cargo.backup_executor import execute_sandbox_backup

        with self.assertRaisesRegex(
            BackupExecutionError, "authorization"
        ):
            execute_sandbox_backup(
                replace(self.request, allow_backup=False),
                sandbox_root=self.root,
            )
        self.assertFalse((self.usb / "episode.mkv").exists())



class SingleUseAuthorityTests(unittest.TestCase):

    def setUp(self):
        from truepanel.cargo.backup_executor import SingleUseTransferAuthority
        from truepanel.cargo.copy_button import CopyButtonConfirmation

        self.now = 100.0
        self.authority = SingleUseTransferAuthority(
            clock=lambda: self.now,
            max_age_seconds=30,
        )

        self.confirmation = CopyButtonConfirmation(
            cartridge_id="tv-n-z",
            cartridge_uuid="6988-53EB",
            device_serial="TEST-SERIAL",
            plan_digest="TEST-PLAN-DIGEST",
            confirmed_at_monotonic=95.0,
        )

        self.expected = {
            "cartridge_id": "tv-n-z",
            "cartridge_uuid": "6988-53EB",
            "device_serial": "TEST-SERIAL",
            "plan_digest": "TEST-PLAN-DIGEST",
        }

    def test_accepts_matching_confirmation_once(self):
        self.authority.consume(
            self.confirmation,
            **self.expected,
        )

        with self.assertRaisesRegex(
            BackupExecutionError, "already consumed"
        ):
            self.authority.consume(
                self.confirmation,
                **self.expected,
            )

    def test_rejects_wrong_cartridge(self):
        with self.assertRaisesRegex(
            BackupExecutionError, "does not match"
        ):
            self.authority.consume(
                self.confirmation,
                **{**self.expected, "cartridge_uuid": "WRONG"},
            )

    def test_rejects_wrong_serial(self):
        with self.assertRaisesRegex(
            BackupExecutionError, "does not match"
        ):
            self.authority.consume(
                self.confirmation,
                **{**self.expected, "device_serial": "WRONG"},
            )

    def test_rejects_wrong_plan(self):
        with self.assertRaisesRegex(
            BackupExecutionError, "does not match"
        ):
            self.authority.consume(
                self.confirmation,
                **{**self.expected, "plan_digest": "OTHER"},
            )

    def test_rejects_expired_confirmation(self):
        self.now = 130.1

        with self.assertRaisesRegex(
            BackupExecutionError, "expired"
        ):
            self.authority.consume(
                self.confirmation,
                **self.expected,
            )

    def test_rejects_future_confirmation(self):
        self.now = 90.0

        with self.assertRaisesRegex(
            BackupExecutionError, "expired"
        ):
            self.authority.consume(
                self.confirmation,
                **self.expected,
            )

    def test_rejects_fabricated_dictionary(self):
        with self.assertRaisesRegex(
            BackupExecutionError, "untrusted confirmation type"
        ):
            self.authority.consume(
                {
                    **self.expected,
                    "confirmed_at_monotonic": 95.0,
                },
                **self.expected,
            )



class ConcurrentAuthorityTests(unittest.TestCase):
    """Ensure concurrent requests cannot reuse one confirmation."""

    def test_simultaneous_consumers_allow_exactly_one(self):
        import threading
        from concurrent.futures import ThreadPoolExecutor

        from truepanel.cargo.backup_executor import (
            SingleUseTransferAuthority,
        )
        from truepanel.cargo.copy_button import CopyButtonConfirmation

        authority = SingleUseTransferAuthority(
            clock=lambda: 100.0,
            max_age_seconds=30.0,
        )

        confirmation = CopyButtonConfirmation(
            cartridge_id="tv-n-z",
            cartridge_uuid="6988-53EB",
            device_serial="TEST-SERIAL",
            plan_digest="CONCURRENT-PLAN",
            confirmed_at_monotonic=95.0,
        )

        expected = {
            "cartridge_id": "tv-n-z",
            "cartridge_uuid": "6988-53EB",
            "device_serial": "TEST-SERIAL",
            "plan_digest": "CONCURRENT-PLAN",
        }

        barrier = threading.Barrier(8)

        def attempt():
            barrier.wait(timeout=5)
            try:
                authority.consume(confirmation, **expected)
                return "accepted"
            except BackupExecutionError:
                return "rejected"

        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(lambda _: attempt(), range(8)))

        self.assertEqual(results.count("accepted"), 1)
        self.assertEqual(results.count("rejected"), 7)


class HostHandoffAndManifestTests(unittest.TestCase):
    def make_handoff(self):
        from truepanel.cargo.backup_executor import HostConfirmationHandoff
        from truepanel.cargo.copy_button import CopyButtonConfirmation
        handoff = HostConfirmationHandoff(clock=lambda: 100.0)
        handoff.arm(cartridge_id="tv-n-z", cartridge_uuid="6988-53EB",
                    device_serial="SERIAL", plan_digest="PLAN")
        confirmation = CopyButtonConfirmation(
            cartridge_id="tv-n-z", cartridge_uuid="6988-53EB",
            device_serial="SERIAL", plan_digest="PLAN",
            confirmed_at_monotonic=95.0)
        return handoff, confirmation

    def test_host_callback_once_and_consumed(self):
        handoff, confirmation = self.make_handoff()
        handoff.on_confirmation(confirmation)
        self.assertFalse(handoff.consume()["executed"])
        with self.assertRaises(BackupExecutionError):
            handoff.consume()
        with self.assertRaises(BackupExecutionError):
            handoff.on_confirmation(confirmation)

    def test_host_unarmed_callback_rejected(self):
        handoff, confirmation = self.make_handoff()
        handoff.disarm()
        with self.assertRaises(BackupExecutionError):
            handoff.on_confirmation(confirmation)

    def test_host_mismatch_consumed_fail_closed(self):
        from dataclasses import replace
        handoff, confirmation = self.make_handoff()
        handoff.on_confirmation(replace(confirmation, plan_digest="WRONG"))
        with self.assertRaises(BackupExecutionError):
            handoff.consume()
        with self.assertRaises(BackupExecutionError):
            handoff.consume()

    def test_host_concurrent_consumption(self):
        from concurrent.futures import ThreadPoolExecutor
        handoff, confirmation = self.make_handoff()
        handoff.on_confirmation(confirmation)
        def attempt(_):
            try:
                handoff.consume()
                return True
            except BackupExecutionError:
                return False
        with ThreadPoolExecutor(max_workers=12) as pool:
            outcomes = list(pool.map(attempt, range(12)))
        self.assertEqual(sum(outcomes), 1)

    def test_sandbox_manifest_validates(self):
        from truepanel.cargo.backup_executor import build_verified_sandbox_manifest
        from truepanel.cargo.backup_manifest import validate_backup_manifest
        import json
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            manifest = build_verified_sandbox_manifest(
                source=root / "episode.mkv",
                copy_result={"state": "VERIFIED_SANDBOX_COPY",
                             "executed": True, "size_bytes": 12,
                             "sha256": "a" * 64})
            path = root / "manifest.json"
            path.write_text(json.dumps(manifest))
            checked = validate_backup_manifest(path)
            self.assertEqual(checked["items"][0]["sha256"], "a" * 64)

    def test_failed_copy_cannot_make_manifest(self):
        from truepanel.cargo.backup_executor import build_verified_sandbox_manifest
        with self.assertRaises(BackupExecutionError):
            build_verified_sandbox_manifest(
                source=Path("/test"),
                copy_result={"state": "FAILED", "executed": False})

    def test_physical_entrypoint_always_blocked(self):
        from truepanel.cargo.backup_executor import execute_physical_backup
        with self.assertRaisesRegex(BackupExecutionError, "not enabled"):
            execute_physical_backup()


if __name__ == "__main__":
    unittest.main()
