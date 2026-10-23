"""No-systemd regression tests for one-line Mission Control activation."""
from __future__ import annotations

import unittest
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


if __name__ == "__main__":
    unittest.main()
