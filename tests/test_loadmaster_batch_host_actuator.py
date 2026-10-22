"""Nonphysical host-batch actuator safety tests."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from truepanel.cargo.batch_authorization import BatchApprovalScope, BatchItem
from truepanel.cargo.batch_host_actuator import execute_host_batch_core
from truepanel.cargo.backup_executor import BackupExecutionError


class Window:
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False


class ActuatorGateTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        self.nas = root/'nas'
        self.usb = root/'usb'
        self.nas.mkdir(); self.usb.mkdir()
        self.mount = root/'mount'
        self.mount.mkdir()
        self.manifest = root/'manifest.json'
        self.items = (BatchItem('Show/a.mkv', 10, 'a'*64),)
        self.scope = BatchApprovalScope(cartridge_id='tv-n-z',
            cartridge_uuid='6988-53EB', items=self.items)
        self.bridge = Mock()
        self.bridge.consume_read_only.return_value = {
            'state': 'HOST_APPROVAL_EVIDENCE_ONLY',
            'physical_execution_enabled': False, 'executed': False,
            'cartridge_id':'tv-n-z', 'plan_digest':self.scope.digest}

    def run_core(self, reattest=None):
        return execute_host_batch_core(scope=self.scope, bridge=self.bridge,
            reattest=reattest or (lambda: self.items),
            nas=self.nas, usb=self.usb, mount=self.mount,
            by_id='/dev/disk/by-id/mock', uuid='6988-53EB',
            manifest=self.manifest, writable_session=Window())

    def test_changed_batch_never_consumes_confirmation(self):
        with self.assertRaisesRegex(BackupExecutionError, 'changed'):
            self.run_core(lambda: ())
        self.bridge.consume_read_only.assert_not_called()

    def test_replay_refused_before_copy(self):
        source = self.nas/'Show/a.mkv'
        source.parent.mkdir()
        source.write_bytes(b'x'*10)
        with patch('truepanel.cargo.batch_host_actuator._writable_identity'), patch(
            'truepanel.cargo.batch_host_actuator._copy_validated_roots',
            return_value={'sha256':'a'*64}) as copy, patch(
            'truepanel.cargo.batch_host_actuator.commit_verified_backup'):
            self.run_core()
            with self.assertRaises(BackupExecutionError):
                self.run_core()
        copy.assert_called_once()

    def test_existing_file_never_overwritten(self):
        source = self.nas/'Show/a.mkv'
        source.parent.mkdir()
        source.write_bytes(b'x'*10)
        target = self.usb/'Show/a.mkv'
        target.parent.mkdir()
        target.write_bytes(b'old!')
        with patch('truepanel.cargo.batch_host_actuator._writable_identity'), patch(
            'truepanel.cargo.batch_host_actuator._copy_validated_roots') as copy:
            with self.assertRaisesRegex(BackupExecutionError, 'occupied'):
                self.run_core()
        copy.assert_not_called()
        self.assertEqual(target.read_bytes(), b'old!')

    def test_recheck_stops_between_items(self):
        self.items = (self.items[0], BatchItem('Show/b.mkv',10,'b'*64))
        self.scope = BatchApprovalScope(cartridge_id='tv-n-z',
            cartridge_uuid='6988-53EB', items=self.items)
        self.bridge.consume_read_only.return_value['plan_digest'] = self.scope.digest
        source = self.nas/'Show/a.mkv'
        source.parent.mkdir()
        source.write_bytes(b'x'*10)
        state = [0]
        def check():
            state[0] += 1
            return self.items if state[0] < 3 else ()
        with patch('truepanel.cargo.batch_host_actuator._writable_identity'), patch(
            'truepanel.cargo.batch_host_actuator._copy_validated_roots',
            return_value={'sha256':'a'*64}) as copy, patch(
            'truepanel.cargo.batch_host_actuator.commit_verified_backup'):
            with self.assertRaisesRegex(BackupExecutionError, 'changed'):
                self.run_core(check)
        copy.assert_called_once()


if __name__ == '__main__':
    unittest.main()
