"""Deterministic timing regressions for physical confirmation, no hardware."""
import unittest

from truepanel.cargo.copy_button import (
    DEFAULT_CONFIRMATION_WINDOW_SECONDS, LoadmasterCopyButtonGate,
    LoadmasterPhysicalPreflight,
)


class PhysicalTimingTests(unittest.TestCase):
    def setUp(self):
        self.time = 100.0
        self.level = 1
        self.gate = LoadmasterCopyButtonGate(
            read_level=lambda: self.level, clock=lambda: self.time
        )
        self.ready = LoadmasterPhysicalPreflight(
            cartridge_id='tv-n-z', cartridge_uuid='6988-53EB',
            device_serial='2532EA8D3DC7', plan_state='READY',
            backup_files=1, backup_bytes=533754539,
            baseline_verified=True, identity_verified=True,
            backlog_verified=True, plan_digest='a' * 64,
            generated_at_monotonic=self.time,
        )

    def poll_at(self, seconds, level):
        self.time = 100.0 + seconds
        self.level = level
        return self.gate.poll()

    def test_clean_press_within_window_confirms_once(self):
        self.gate.arm(self.ready)
        self.assertIsNone(self.poll_at(0.1, 1))
        self.assertIsNone(self.poll_at(12.0, 0))
        accepted = self.poll_at(12.11, 0)
        self.assertIsNotNone(accepted)
        self.assertEqual(accepted.plan_digest, 'a' * 64)
        self.assertIsNone(self.poll_at(12.5, 0))
        self.assertIsNone(self.poll_at(12.6, 1))
        self.assertIsNone(self.poll_at(12.8, 1))

    def test_late_press_never_confirms(self):
        self.gate.arm(self.ready)
        self.poll_at(0.1, 1)
        self.poll_at(DEFAULT_CONFIRMATION_WINDOW_SECONDS + 0.1, 0)
        self.assertIsNone(self.poll_at(DEFAULT_CONFIRMATION_WINDOW_SECONDS + 0.21, 0))
        self.assertFalse(self.gate.armed_snapshot()['armed'])

    def test_sub_debounce_glitch_ignored(self):
        self.gate.arm(self.ready)
        self.poll_at(0.1, 1)
        self.poll_at(1.0, 0)
        self.poll_at(1.03, 1)
        self.assertIsNone(self.poll_at(1.2, 1))
        self.assertTrue(self.gate.armed_snapshot()['armed'])

    def test_no_press_before_arm_can_authorize(self):
        self.poll_at(0.1, 1)
        self.poll_at(1.0, 0)
        self.assertIsNone(self.poll_at(1.1, 0))
        self.gate.arm(self.ready)
        self.assertIsNone(self.poll_at(1.2, 0))


if __name__ == '__main__':
    unittest.main()
