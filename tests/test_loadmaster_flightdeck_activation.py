"""No-systemd regression tests for one-line Mission Control activation."""
from __future__ import annotations

import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch
from truepanel.cargo import production_flightdeck_activate as activation
from truepanel.cargo.production_flightdeck_activate import (
    patched_config, ActivationHold, SNAPSHOT,
)


class TestMissionControlActivationPatch(unittest.TestCase):
    def setUp(self):
        self.text = (
            "theme_pack: tactical\n"
            "mission_control:\n"
            "  cargo_bay:\n"
            "    enabled: true\n"
            "    loadmaster:\n"
            "      enabled: true\n"
            "      backlog_path: /var/lib/truepanel/loadmaster/pending-cargo.json\n"
            "  fan_health:\n"
            "    enabled: true\n"
        )

    def test_adds_exact_one_line_preserving_everything_else(self):
        changed, applied = patched_config(self.text)
        self.assertTrue(applied)
        self.assertIn(
            "      flight_deck_snapshot_path: " + str(SNAPSHOT), changed)
        self.assertEqual(changed.count("flight_deck_snapshot_path:"), 1)
        self.assertIn("  fan_health:\n    enabled: true\n", changed)
        self.assertTrue(changed.startswith("theme_pack: tactical"))

    def test_idempotent_reapply(self):
        changed, applied = patched_config(self.text)
        again, modified = patched_config(changed)
        self.assertFalse(modified)
        self.assertEqual(again, changed)

    def test_different_preexisting_snapshot_must_not_be_replaced(self):
        source = self.text.replace(
            "      backlog_path:",
            "      flight_deck_snapshot_path: /other/file.json\n"
            "      backlog_path:")
        with self.assertRaisesRegex(ActivationHold, "another Flight Deck"):
            patched_config(source)

    def test_loadmaster_disabled_refuses(self):
        disabled = self.text.replace(
            "    loadmaster:\n      enabled: true",
            "    loadmaster:\n      enabled: false")
        with self.assertRaisesRegex(ActivationHold, "not enabled"):
            patched_config(disabled)

    def test_other_yaml_structure_refused(self):
        text = self.text.replace(
            "    loadmaster:\n",
            "      loadmaster:\n")
        with self.assertRaises(ActivationHold):
            patched_config(text)

    def test_multiple_blocks_not_allowed(self):
        with self.assertRaisesRegex(ActivationHold, "unique"):
            patched_config(self.text + "    loadmaster:\n      enabled: true\n")

    def test_duplicate_mentioned_key_refuses(self):
        with self.assertRaisesRegex(ActivationHold, "ambiguously"):
            patched_config(self.text + "# flight_deck_snapshot_path: duplicate\n")

    def test_unknown_yaml_refuses(self):
        with self.assertRaises(ActivationHold):
            patched_config("!untrusted-object\n")



class TestActivationAtomicity(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="loadmaster-activation-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.config = self.root / "truepanel.yaml"
        self.source = (
            "mission_control:\\n  cargo_bay:\\n    enabled: true\\n"
            "    loadmaster:\\n      enabled: true\\n"
            "      backlog_path: /var/lib/truepanel/loadmaster/pending-cargo.json\\n"
        )
        self.config.write_text(self.source)
        self.backups = self.root / "backups"
        self.backups.mkdir()

    def activation_context(self):
        from contextlib import ExitStack
        stack = ExitStack()
        stack.enter_context(patch.object(activation, "CONFIG", self.config))
        stack.enter_context(patch.object(activation, "BACKUPS", self.backups))
        stack.enter_context(patch.object(activation, "STATE", self.root))
        stack.enter_context(patch.object(activation, "_private"))
        stack.enter_context(patch.object(activation, "_installed_path_valid"))
        stack.enter_context(patch.object(activation, "read_flightdeck",
                                         return_value={"state": "READY"}))
        stack.enter_context(patch.object(activation.os, "geteuid", return_value=0))
        return stack

    def test_config_activation_preserves_backup_and_original_settings(self):
        with self.activation_context(), patch.object(activation, "_restart_healthy"):
            result = activation.activate(apply=True)
        self.assertEqual(result["state"], "LOADMASTER_UI_CONNECTED")
        self.assertEqual(len(list(self.backups.glob("*.yaml"))), 1)
        self.assertEqual(next(self.backups.glob("*.yaml")).read_text(), self.source)
        self.assertIn("flight_deck_snapshot_path", self.config.read_text())

    def test_failed_restart_rolls_back_exact_original_yaml(self):
        with self.activation_context(), patch.object(
                activation, "_restart_healthy", side_effect=[
                    RuntimeError("restart refused"), None]) as restart:
            with self.assertRaisesRegex(activation.ActivationHold, "restored"):
                activation.activate(apply=True)
        self.assertEqual(self.config.read_text(), self.source)
        self.assertEqual(restart.call_count, 2)

if __name__ == "__main__":
    unittest.main()
