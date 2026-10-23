"""No-hardware runner tests for TV N-Z attended export and dual RO protections."""
from __future__ import annotations

import io
import unittest
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
from unittest.mock import MagicMock, patch

from truepanel.cargo.backup_executor import BackupExecutionError
from truepanel.cargo.bidirectional_host_scope import CargoAction, CargoScope
from tools import loadmaster_tv_nz_supervised_live_fire as runner


def fixture_scope():
    from tools.loadmaster_tv_nz_hdd_export_scope import (
        EXPECTED_BYTES, EXPECTED_SHA256,
    )
    return CargoScope(
        "tv-n-z", runner.TV_NZ_UUID, runner.TV_NZ_SERIAL,
        (CargoAction(
            "NAS_TO_USB", runner.TV_NZ_TEST_RELATIVE,
            EXPECTED_BYTES, EXPECTED_SHA256),),
        attempt_nonce="5" * 32)


class TestTvNzProductionRunner(unittest.TestCase):
    def test_default_readonly_preview_does_not_acquire_gpio(self):
        scope = fixture_scope()
        output = io.StringIO()
        with patch.object(runner, "_scope", return_value=scope), \
             patch.object(runner, "HostOwnershipGuard") as owner, \
             patch.object(runner, "FintekCopyButtonReader") as gpio, \
             patch.object(runner, "execute_one_export") as physical, \
             redirect_stdout(output):
            result = runner.execute()
        self.assertEqual(result, 0)
        self.assertIn("TV_NZ_ONE_FILE_READ_ONLY_READY", output.getvalue())
        self.assertIn('"usb_written": false', output.getvalue())
        self.assertNotIn("ARMED:", output.getvalue())
        owner.assert_not_called()
        gpio.assert_not_called()
        physical.assert_not_called()

    def test_live_flags_both_required(self):
        with patch.object(runner, "_scope", return_value=fixture_scope()), \
             patch.object(runner, "HostOwnershipGuard") as owner, \
             redirect_stdout(io.StringIO()):
            for kwargs in (
                {"live": True, "operator_present": False,
                 "accept_degraded_pool": True},
                {"live": True, "operator_present": True,
                 "accept_degraded_pool": False},
            ):
                with self.subTest(kwargs=kwargs):
                    with self.assertRaisesRegex(BackupExecutionError, "flags"):
                        runner.execute(**kwargs)
            owner.assert_not_called()

    def test_production_gpio_owner_blocks_even_with_flags(self):
        with patch.object(runner, "_scope", return_value=fixture_scope()), \
             patch.object(runner.os, "geteuid", return_value=0), \
             patch.object(runner, "_service_active", return_value=True), \
             patch.object(runner, "HostOwnershipGuard") as owner, \
             redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(BackupExecutionError, "GPIO already occupied"):
                runner.execute(live=True, operator_present=True,
                               accept_degraded_pool=True)
            owner.assert_not_called()

    def test_mission_control_loss_blocks_physical_runner(self):
        def active(service):
            return service == "truepanel.service"
        with patch.object(runner, "_scope", return_value=fixture_scope()), \
             patch.object(runner.os, "geteuid", return_value=0), \
             patch.object(runner, "_service_active", return_value=False), \
             patch.object(runner, "HostOwnershipGuard") as owner, \
             redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(BackupExecutionError, "Mission Control"):
                runner.execute(live=True, operator_present=True,
                               accept_degraded_pool=True)
            owner.assert_not_called()

    def test_guard_and_timer_use_exact_tv_nz_rescue(self):
        scope = fixture_scope()
        issued = []
        def call(command, **kw):
            issued.append(command)
            return "Running as unit"
        with patch.object(runner, "_root_only"), \
             patch.object(runner, "mount_mode", return_value="ro"), \
             patch.object(runner, "owner_start_ticks", return_value=7891), \
             patch.object(runner, "verify_independent_guard", return_value=True), \
             patch.object(runner, "_unit_fields",
                          return_value={"LoadState": "loaded", "ActiveState": "active"}), \
             patch.object(runner, "_call", side_effect=call), \
             patch.object(Path, "exists", return_value=False), \
             patch.object(Path, "is_symlink", return_value=False):
            guardian, rescue = runner._guard_and_rescue(scope)
            self.assertTrue(guardian())
            self.assertTrue(rescue())
        self.assertEqual(len(issued), 2)
        guardian_cmd, timer_cmd = issued
        self.assertIn("tools.loadmaster_tv_nz_ro_guard", guardian_cmd)
        self.assertIn("--watch", guardian_cmd)
        self.assertIn("--property=PrivateMounts=no", guardian_cmd)
        self.assertIn("--lease-seconds", guardian_cmd)
        self.assertIn("150", guardian_cmd)
        self.assertIn("tools.loadmaster_tv_nz_ro_guard", timer_cmd)
        self.assertIn("--rescue", timer_cmd)
        self.assertIn("--on-active=175s", timer_cmd)
        self.assertIn("--timer-property=AccuracySec=1s", timer_cmd)
        self.assertIn("--property=PrivateMounts=no", timer_cmd)
        self.assertNotIn("--live-fire", guardian_cmd + timer_cmd)
        self.assertNotIn("remount,rw", guardian_cmd + timer_cmd)

    def test_timer_activation_loss_fails_closed(self):
        scope = fixture_scope()
        with patch.object(runner, "_root_only"), \
             patch.object(runner, "mount_mode", return_value="ro"), \
             patch.object(runner, "owner_start_ticks", return_value=7891), \
             patch.object(runner, "verify_independent_guard", return_value=True), \
             patch.object(runner, "_unit_fields",
                          return_value={"LoadState": "loaded", "ActiveState": "inactive"}), \
             patch.object(runner, "_call", return_value="Running as unit"), \
             patch.object(Path, "exists", return_value=False), \
             patch.object(Path, "is_symlink", return_value=False):
            with self.assertRaisesRegex(BackupExecutionError, "not armed"):
                runner._guard_and_rescue(scope)

    def test_real_usb_never_automatically_receives_default_preview(self):
        with patch.object(runner, "_scope", side_effect=BackupExecutionError("not RO")), \
             patch.object(runner, "_service_active") as service, \
             redirect_stderr(io.StringIO()):
            self.assertEqual(runner.main([]), 2)
            service.assert_not_called()

    def test_operator_confirmation_is_not_auto_generated(self):
        # Synthetic preview does not construct a session or press GPIO.
        with patch.object(runner, "_scope", return_value=fixture_scope()), \
             patch.object(runner, "LoadmasterHostSessionBridge") as bridge, \
             patch.object(runner, "LoadmasterCopyButtonService") as button, \
             redirect_stdout(io.StringIO()):
            runner.main([])
            bridge.assert_not_called()
            button.assert_not_called()


if __name__ == "__main__":
    unittest.main()
