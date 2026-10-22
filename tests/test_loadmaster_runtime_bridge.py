"""Host integration: evidence-only, no USB operations."""
import unittest
from unittest.mock import Mock
from truepanel.host.runtime import HostAgentRuntime


class RuntimeBridgeTests(unittest.TestCase):
    def make_runtime(self, bridge=None, service=None, guard=None):
        safety = Mock()
        fan = Mock()
        rt = HostAgentRuntime(
            fan_runtime=fan, safety=safety,
            fan_server_factory=lambda: None,
            ownership_guard=guard,
            loadmaster_copy_button_service=service,
            loadmaster_session_bridge=bridge,
        )
        return rt

    def test_disabled_session_denied(self):
        rt = self.make_runtime()
        rt.start()
        with self.assertRaisesRegex(RuntimeError, 'disabled'):
            rt.prepare_loadmaster_session(object())
        rt.shutdown()

    def test_prepare_and_consume_bridge(self):
        bridge, service = Mock(), Mock()
        bridge.prepare_and_arm.return_value = {'state': 'HOST_ARMED_EVIDENCE_ONLY'}
        bridge.consume_read_only.return_value = {'executed': False}
        rt = self.make_runtime(bridge, service)
        rt.start()
        self.assertFalse(rt.consume_loadmaster_session_read_only()['executed'])
        self.assertEqual(rt.prepare_loadmaster_session('spec')['state'], 'HOST_ARMED_EVIDENCE_ONLY')
        bridge.prepare_and_arm.assert_called_once_with('spec')
        rt.shutdown()
        bridge.disarm.assert_called_once()
        service.stop.assert_called_once()

    def test_direct_arm_blocked_when_bridge_present(self):
        rt = self.make_runtime(Mock(), Mock())
        rt.start()
        with self.assertRaisesRegex(RuntimeError, 'direct arm disabled'):
            rt.arm_loadmaster_copy_button(object())
        rt.shutdown()

    def test_direct_arm_blocked_without_bridge(self):
        service = Mock()
        rt = self.make_runtime(None, service)
        rt.start()
        with self.assertRaisesRegex(RuntimeError, 'direct arm disabled'):
            rt.arm_loadmaster_copy_button(object())
        service.arm.assert_not_called()
        rt.shutdown()

    def test_prestart_and_postshutdown_blocked(self):
        rt = self.make_runtime(Mock(), Mock())
        with self.assertRaisesRegex(RuntimeError, 'not running'):
            rt.prepare_loadmaster_session('spec')
        rt.start()
        rt.shutdown()
        with self.assertRaisesRegex(RuntimeError, 'not running'):
            rt.consume_loadmaster_session_read_only()

    def test_ownership_guard_checked(self):
        guard = Mock()
        rt = self.make_runtime(Mock(), Mock(), guard)
        with self.assertRaisesRegex(RuntimeError, 'does not own'):
            rt.prepare_loadmaster_session('spec')

    def test_shutdown_disarms_even_if_failure(self):
        bridge = Mock()
        bridge.disarm.side_effect = RuntimeError('oops')
        service = Mock()
        rt = self.make_runtime(bridge, service)
        rt.start()
        rt.shutdown()
        service.stop.assert_called_once()


if __name__ == '__main__':
    unittest.main()
