"""No-hardware checks for the narrowly scoped TV N-Z physical executor."""
from __future__ import annotations

import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from truepanel.cargo.backup_executor import BackupExecutionError
from truepanel.cargo.bidirectional_host_scope import CargoAction, CargoScope
from truepanel.cargo.supervised_mount import SupervisedWriteWindow
from truepanel.cargo import tv_nz_supervised_export as pilot


class Bridge:
    def __init__(self, scope):
        self.scope = scope
        self.calls = 0
        self.evidence = None

    def consume_read_only(self):
        self.calls += 1
        if self.calls > 1:
            raise BackupExecutionError("approval already spent")
        if self.evidence is not None:
            return self.evidence
        return {
            "state": "HOST_APPROVAL_EVIDENCE_ONLY",
            "cartridge_id": self.scope.cartridge_id,
            "plan_digest": self.scope.digest,
            "executed": False,
            "physical_execution_enabled": False,
        }


class TestTvNzActuator(unittest.TestCase):
    def setUp(self):
        self.action = CargoAction(
            "NAS_TO_USB", pilot.TV_NZ_TEST_RELATIVE,
            pilot.EXPECTED_BYTES, pilot.EXPECTED_SHA256)
        self.scope = CargoScope(
            "tv-n-z", pilot.TV_NZ_UUID, pilot.TV_NZ_SERIAL,
            (self.action,), attempt_nonce="0" * 32)
        self.bridge = Bridge(self.scope)
        self.window = SupervisedWriteWindow(
            mount=pilot.TV_NZ_MOUNT, uuid=pilot.TV_NZ_UUID,
            by_id=pilot.TV_NZ_BY_ID)
        self.watch = MagicMock(return_value=True)
        self.timer = MagicMock(return_value=True)
        self.timeline = []
        self.mocks = [
            patch.object(pilot, "_root_only"),
            patch.object(pilot, "_attest_ro",
                         side_effect=lambda: self.timeline.append("RO")),
            patch.object(pilot, "_fresh_action"),
            patch.object(pilot, "_writable_identity",
                         side_effect=lambda **kwargs: self.timeline.append("RW")),
            patch.object(pilot, "qualify_read_only", return_value={
                "state": "TV_NZ_HDD_EXPORT_SCOPE_READ_ONLY_PASS",
                "source_sha256": pilot.EXPECTED_SHA256,
                "size_bytes": pilot.EXPECTED_BYTES,
                "physical_authorized": False,
            }),
            patch.object(pilot.os.path, "lexists", return_value=False),
            patch.object(pilot, "_stat_and_hash", return_value=(
                pilot.EXPECTED_BYTES, pilot.EXPECTED_SHA256)),
            patch.object(pilot, "transfer_one_approved",
                         side_effect=lambda **kw: (
                             self.timeline.append("TRANSFER") or
                             {"state": "NEW_VERIFIED_COPY"})),
            patch.object(pilot, "commit_verified_backup",
                         side_effect=lambda **kw: (
                             self.timeline.append("RECEIPT") or
                             {"state": "EVIDENCE_RECORDED"})),
            patch.object(
                SupervisedWriteWindow, "__enter__",
                side_effect=lambda obj: (self.timeline.append("WINDOW_OPEN") or obj),
                autospec=True),
            patch.object(
                SupervisedWriteWindow, "__exit__",
                side_effect=lambda obj, *args: (
                    self.timeline.append("WINDOW_CLOSED") or False),
                autospec=True),
        ]
        for item in self.mocks:
            item.start()
            self.addCleanup(item.stop)

    def run_pilot(self):
        return pilot.execute_one_export(
            scope=self.scope, bridge=self.bridge,
            writable_session=self.window,
            watchdog_verified=self.watch,
            rescue_timer_verified=self.timer)

    def test_success_writes_receipt_only_after_window_closes(self):
        result = self.run_pilot()
        self.assertEqual(result["state"], "TV_NZ_HDD_EXPORT_VERIFIED")
        self.assertFalse(result["hdd_written"])
        self.assertTrue(result["cartridge_read_only"])
        self.assertEqual(self.bridge.calls, 1)
        self.assertTrue(
            self.timeline.index("WINDOW_CLOSED") <
            self.timeline.index("RECEIPT"))
        self.assertTrue(self.timeline.index("TRANSFER") <
                        self.timeline.index("WINDOW_CLOSED"))
        transport = pilot.transfer_one_approved
        self.assertEqual(
            transport.call_args.kwargs["rsync_timeout_seconds"], 60)

    def test_wrong_direction_rejected_before_approval(self):
        self.scope = CargoScope(
            "tv-n-z", pilot.TV_NZ_UUID, pilot.TV_NZ_SERIAL,
            (CargoAction("USB_TO_NAS", self.action.relative_path,
                         self.action.size_bytes, self.action.sha256),),
            attempt_nonce="0" * 32)
        with self.assertRaisesRegex(BackupExecutionError, "scope"):
            self.run_pilot()
        self.assertEqual(self.bridge.calls, 0)

    def test_wrong_file_hash_rejected(self):
        self.scope = CargoScope(
            "tv-n-z", pilot.TV_NZ_UUID, pilot.TV_NZ_SERIAL,
            (CargoAction("NAS_TO_USB", self.action.relative_path,
                         self.action.size_bytes, "b" * 64),),
            attempt_nonce="0" * 32)
        with self.assertRaisesRegex(BackupExecutionError, "scope"):
            self.run_pilot()
        self.assertEqual(self.bridge.calls, 0)

    def test_wrong_write_window_rejected(self):
        self.window.mount = Path("/mnt/loadmaster-spare-ro")
        with self.assertRaisesRegex(BackupExecutionError, "context"):
            self.run_pilot()
        self.assertEqual(self.bridge.calls, 0)

    def test_timer_missing_prevents_approval(self):
        self.timer.return_value = False
        with self.assertRaisesRegex(BackupExecutionError, "rescue timer"):
            self.run_pilot()
        self.assertEqual(self.bridge.calls, 0)
        self.assertNotIn("WINDOW_OPEN", self.timeline)

    def test_watchdog_missing_prevents_approval(self):
        self.watch.return_value = False
        with self.assertRaisesRegex(BackupExecutionError, "guard"):
            self.run_pilot()
        self.assertEqual(self.bridge.calls, 0)

    def test_preflight_mismatch_prevents_approval(self):
        pilot.qualify_read_only.return_value["source_sha256"] = "b" * 64
        with self.assertRaisesRegex(BackupExecutionError, "readiness"):
            self.run_pilot()
        self.assertEqual(self.bridge.calls, 0)

    def test_wrong_gpio_evidence_never_opens_window(self):
        self.bridge.evidence = {
            "state": "HOST_APPROVAL_EVIDENCE_ONLY",
            "cartridge_id": "tv-n-z", "plan_digest": "a" * 64,
            "executed": False, "physical_execution_enabled": False,
        }
        with self.assertRaisesRegex(BackupExecutionError, "evidence"):
            self.run_pilot()
        self.assertNotIn("WINDOW_OPEN", self.timeline)

    def test_lost_guard_inside_window_aborts_transport(self):
        self.watch.side_effect = [True, False]
        with self.assertRaisesRegex(BackupExecutionError, "guard"):
            self.run_pilot()
        self.assertIn("WINDOW_CLOSED", self.timeline)
        self.assertNotIn("TRANSFER", self.timeline)
        self.assertNotIn("RECEIPT", self.timeline)

    def test_lost_timer_inside_window_aborts_transport(self):
        self.timer.side_effect = [True, False]
        with self.assertRaisesRegex(BackupExecutionError, "timer"):
            self.run_pilot()
        self.assertIn("WINDOW_CLOSED", self.timeline)
        self.assertNotIn("TRANSFER", self.timeline)

    def test_transport_refusing_no_replace_never_records_receipt(self):
        pilot.transfer_one_approved.return_value = {"state": "ALREADY_PUBLISHED_VERIFIED"}
        pilot.transfer_one_approved.side_effect = None
        with self.assertRaisesRegex(BackupExecutionError, "publish"):
            self.run_pilot()
        self.assertIn("WINDOW_CLOSED", self.timeline)
        self.assertNotIn("RECEIPT", self.timeline)

    def test_postflight_ro_failure_never_records_receipt(self):
        pilot._attest_ro.side_effect = [
            None, BackupExecutionError("cartridge no longer RO")]
        with self.assertRaisesRegex(BackupExecutionError, "no longer RO"):
            self.run_pilot()
        self.assertIn("WINDOW_CLOSED", self.timeline)
        self.assertNotIn("RECEIPT", self.timeline)

    def test_postflight_hash_failure_never_records_receipt(self):
        pilot._stat_and_hash.side_effect = [
            (pilot.EXPECTED_BYTES, pilot.EXPECTED_SHA256),
            (pilot.EXPECTED_BYTES, "e" * 64)]
        with self.assertRaisesRegex(BackupExecutionError, "hash mismatch"):
            self.run_pilot()
        self.assertNotIn("RECEIPT", self.timeline)

    def test_extra_physical_file_refused(self):
        self.scope = CargoScope(
            "tv-n-z", pilot.TV_NZ_UUID, pilot.TV_NZ_SERIAL,
            (self.action, CargoAction("NAS_TO_USB", "Other/File.mkv",
                                     40, "a" * 64)), attempt_nonce="0" * 32)
        with self.assertRaisesRegex(BackupExecutionError, "scope"):
            self.run_pilot()
        self.assertEqual(self.bridge.calls, 0)

    def test_destination_occupied_refused_before_gpio(self):
        pilot.os.path.lexists.return_value = True
        with self.assertRaisesRegex(BackupExecutionError, "occupied"):
            self.run_pilot()
        self.assertEqual(self.bridge.calls, 0)


if __name__ == "__main__":
    unittest.main()
