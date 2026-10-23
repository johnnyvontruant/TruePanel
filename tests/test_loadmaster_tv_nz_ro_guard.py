"""Read-only/simulated qualification of the exact TV N-Z RO watchdog."""
from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from truepanel.cargo.backup_executor import BackupExecutionError
from truepanel.cargo import tv_nz_ro_watchdog as guard


def runner(*, uuid="6988-53EB", fs="exfat", options="ro,nosuid,nodev,noexec",
           source="/dev/sda2", target="/mnt/loadmaster-tv-nz-ro"):
    def call(argv):
        if argv[0] == "findmnt":
            return f"{source} {target} exfat {options}"
        if argv[0] == "blkid":
            return uuid if argv[2] == "UUID" else fs
        raise AssertionError(argv)
    return call


def realpath(_):
    return "/dev/sda2"


class PinTests(unittest.TestCase):
    def test_pinned_ro_identity(self):
        self.assertEqual(guard.mount_mode(command=runner(), realpath=realpath), "ro")

    def test_pinned_rw_identity(self):
        self.assertEqual(guard.mount_mode(
            command=runner(options="rw,nosuid,nodev"), realpath=realpath), "rw")

    def test_wrong_uuid_rejected(self):
        with self.assertRaisesRegex(BackupExecutionError, "identity"):
            guard.mount_mode(command=runner(uuid="6ADA-80D5"), realpath=realpath)

    def test_wrong_filesystem_rejected(self):
        with self.assertRaisesRegex(BackupExecutionError, "identity"):
            guard.mount_mode(command=runner(fs="vfat"), realpath=realpath)

    def test_wrong_mount_refused(self):
        with self.assertRaisesRegex(BackupExecutionError, "mount"):
            guard.mount_mode(command=runner(target="/mnt/other"), realpath=realpath)

    def test_source_and_byid_must_resolve_identically(self):
        def different(path):
            return "/dev/sda2" if path == "/dev/sda2" else "/dev/sdz2"
        with self.assertRaisesRegex(BackupExecutionError, "identity"):
            guard.mount_mode(command=runner(), realpath=different)

    def test_ambiguous_mount_modes_refused(self):
        for flags in ("ro,rw", "nodev,noexec"):
            with self.subTest(flags=flags):
                with self.assertRaisesRegex(BackupExecutionError, "ambiguous"):
                    guard.mount_mode(command=runner(options=flags), realpath=realpath)

    def test_noncanonical_pin_rejected(self):
        wrong = replace(guard.TvNzPin(), uuid="6ADA-80D5")
        with self.assertRaisesRegex(BackupExecutionError, "pin"):
            guard.mount_mode(wrong, command=runner(), realpath=realpath)

    def test_existing_symlink_mount_rejected(self):
        with patch.object(Path, "is_symlink", autospec=True, return_value=True):
            with self.assertRaisesRegex(BackupExecutionError, "symlink"):
                guard.mount_mode(command=runner(), realpath=realpath)

    def test_preflight_does_not_start_service_or_mount(self):
        with patch.object(guard, "mount_mode", return_value="ro"):
            result = guard.preflight()
        self.assertEqual(result["state"], "TV_NZ_RO_GUARD_PREFLIGHT_PASS")
        self.assertFalse(result["usb_written"])
        self.assertFalse(result["gpio_armed"])
        self.assertFalse(result["guard_running"])


class RecoveryTests(unittest.TestCase):
    def test_already_ro_never_runs_mount(self):
        calls = []
        result = guard.restore_ro(inspect=lambda _: "ro",
                                  remount_ro=lambda path: calls.append(path))
        self.assertEqual(result, "RESTORED_RO")
        self.assertFalse(calls)

    def test_rw_only_remounts_exact_pin_ro(self):
        state = ["rw"]
        requests = []
        def remount(path):
            requests.append(path)
            state[0] = "ro"
        result = guard.restore_ro(inspect=lambda _: state[0], remount_ro=remount)
        self.assertEqual(result, "RESTORED_RO")
        self.assertEqual(requests, [guard.TV_NZ_MOUNT])

    def test_unknown_identity_cannot_remount(self):
        calls = []
        with self.assertRaisesRegex(BackupExecutionError, "qualif"):
            guard.restore_ro(inspect=lambda _: "unknown",
                             remount_ro=lambda path: calls.append(path))
        self.assertEqual(calls, [])

    def test_failed_restoration_reports_critical(self):
        with self.assertRaisesRegex(BackupExecutionError, "CRITICAL"):
            guard.restore_ro(inspect=lambda _: "rw", remount_ro=lambda _: None)

    def test_guard_owner_exit_restores_ro(self):
        state = ["ro"]
        owner_calls = [0]
        reports = []
        requests = []
        clock = [1.0]
        def alive(_pid, _ticks):
            owner_calls[0] += 1
            return owner_calls[0] <= 2
        def remount(path):
            requests.append(path)
            state[0] = "ro"
        def nap(_seconds):
            state[0] = "rw"
            clock[0] += .2
        outcome = guard.guard_loop(
            pin=guard.TvNzPin(), owner_pid=145, owner_ticks=12345,
            deadline=15.0, report=reports.append,
            inspect=lambda _: state[0], owner_alive=alive,
            remount_ro=remount, now=lambda: clock[0], pause=nap)
        self.assertEqual(outcome, "RESTORED_RO")
        self.assertEqual(reports, ["READY", "RESTORED_RO"])
        self.assertEqual(requests, [guard.TV_NZ_MOUNT])

    def test_guard_refuses_starting_rw(self):
        with self.assertRaisesRegex(BackupExecutionError, "start RO"):
            guard.guard_loop(
                pin=guard.TvNzPin(), owner_pid=145, owner_ticks=123,
                deadline=14.0, report=lambda _: None,
                inspect=lambda _: "rw",
                owner_alive=lambda p, t: True,
                now=lambda: 1.0)

    def test_guard_refuses_unqualified_owner(self):
        with self.assertRaisesRegex(BackupExecutionError, "lease"):
            guard.guard_loop(
                pin=guard.TvNzPin(), owner_pid=1, owner_ticks=123,
                deadline=14.0, report=lambda _: None,
                inspect=lambda _: "ro",
                owner_alive=lambda p, t: True,
                now=lambda: 1.0)

    def test_guard_refuses_expired_lease(self):
        with self.assertRaisesRegex(BackupExecutionError, "lease"):
            guard.guard_loop(
                pin=guard.TvNzPin(), owner_pid=200, owner_ticks=123,
                deadline=1.0, report=lambda _: None,
                inspect=lambda _: "ro",
                owner_alive=lambda p, t: True,
                now=lambda: 1.0)


class HostQualificationContracts(unittest.TestCase):
    def test_smoke_test_starts_exact_ro_only_guard(self):
        from tools.loadmaster_tv_nz_ro_qualification import build_guard_command
        args = build_guard_command(
            unit="loadmaster-ro-guard-aaaaaaaaaaaa.service",
            owner=200, ticks=500, digest="b" * 64,
            nonce="a" * 32,
            status=Path("/mnt/SSDs/Applications/Loadmaster-Watchdog-Qualification/tv-nz-ro-qualification/a.json"))
        self.assertIn("tools.loadmaster_tv_nz_ro_guard", args)
        self.assertIn("--watch", args)
        self.assertIn("--property=PrivateMounts=no", args)
        self.assertNotIn("--rescue", args)
        self.assertNotIn("rw", args)
        self.assertNotIn("--live-fire", args)

    def test_smoke_test_default_is_non_actuating(self):
        from tools import loadmaster_tv_nz_ro_qualification as command
        with patch.object(command, "preflight", return_value={"state": "PASS"}) as check, \
             patch.object(command, "qualify_read_only_guard") as live:
            self.assertEqual(command.main([]), 0)
            check.assert_called_once()
            live.assert_not_called()


class CommandTests(unittest.TestCase):
    def test_preflight_is_non_actuating(self):
        from tools import loadmaster_tv_nz_ro_guard as command
        with patch.object(command, "preflight", return_value={"state": "PASS"}):
            self.assertEqual(command.main(["--preflight"]), 0)

    def test_rescue_only_in_host_mount_namespace(self):
        from tools import loadmaster_tv_nz_ro_guard as command
        with patch.object(command.os, "geteuid", return_value=0), \
             patch.object(command, "same_host_mount_namespace", return_value=False):
            with self.assertRaisesRegex(BackupExecutionError, "host mount namespace"):
                command.main(["--rescue"])

    def test_rescue_never_asks_for_rw(self):
        from tools import loadmaster_tv_nz_ro_guard as command
        with patch.object(command.os, "geteuid", return_value=0), \
             patch.object(command, "same_host_mount_namespace", return_value=True), \
             patch.object(command, "restore_ro", return_value="RESTORED_RO") as restore:
            self.assertEqual(command.main(["--rescue"]), 0)
            restore.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
