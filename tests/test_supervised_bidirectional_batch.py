"""Purely local simulated host integration, never accesses real USB/GPIO."""
import hashlib
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from truepanel.cargo.backup_executor import BackupExecutionError
from truepanel.cargo.bidirectional_host_scope import CargoScope, inspect_bidirectional
from truepanel.cargo.supervised_bidirectional_batch import (
    execute_supervised_bidirectional_batch, transfer_one_approved)
from truepanel.cargo.ingest_receipts import record_verified_ingest


class Bridge:
    def __init__(self, scope):
        self.scope = scope
        self.calls = 0

    def consume_read_only(self):
        self.calls += 1
        if self.calls > 1:
            raise BackupExecutionError('approval already consumed')
        return {'state': 'HOST_APPROVAL_EVIDENCE_ONLY', 'cartridge_id': self.scope.cartridge_id,
                'plan_digest': self.scope.digest, 'physical_execution_enabled': False,
                'executed': False}


class Window:
    def __init__(self):
        self.entered = self.exited = False

    def __enter__(self):
        self.entered = True
        return self

    def __exit__(self, *args):
        self.exited = True


class TestSupervisedBidirectionalBatch(unittest.TestCase):
    def setUp(self):
        self.usb_tmp = tempfile.TemporaryDirectory(prefix='loadmaster-c9-usb-')
        Path('/mnt/SSDs').mkdir(exist_ok=True)
        self.nas_tmp = tempfile.TemporaryDirectory(prefix='loadmaster-c9-nas-', dir='/mnt/SSDs')
        self.usb_mount = Path(self.usb_tmp.name)
        self.usb = self.usb_mount / 'files'
        self.usb.mkdir()
        self.nas = Path(self.nas_tmp.name)
        self.bak_manifest = self.nas / 'manifest.json'
        self.ingest_root = self.nas / 'receipts'
        self.ingest_root.mkdir(mode=0o700)
        self.serial = 'ABCDEF1234'
        self.uuid = '6ADA-80D5'
        self.entries = (('NAS_TO_USB', 'Export/alpha.bin'),
                        ('USB_TO_NAS', 'Ingest/beta.bin'))
        (self.nas / 'Export').mkdir()
        (self.usb / 'Ingest').mkdir()
        (self.nas / 'Export/alpha.bin').write_bytes(b'from-nas' * 100)
        (self.usb / 'Ingest/beta.bin').write_bytes(b'from-usb' * 100)
        self.scope = CargoScope('spare-lab', self.uuid, self.serial,
            inspect_bidirectional(nas_root=self.nas, usb_root=self.usb, entries=self.entries))

    def tearDown(self):
        self.nas_tmp.cleanup()
        self.usb_tmp.cleanup()

    def invoke(self, *, bridge=None, watchdog=None, identity=None, write_session=None):
        def record(action, source, target):
            return record_verified_ingest(receipt_root=self.ingest_root,
                cartridge_id=self.scope.cartridge_id, cartridge_uuid=self.scope.cartridge_uuid,
                device_serial=self.scope.device_serial, action=action,
                source=source, destination=target)
        return execute_supervised_bidirectional_batch(scope=self.scope,
            bridge=bridge or Bridge(self.scope), nas_root=self.nas,
            usb_root=self.usb, mount=self.usb_mount,
            by_id='/dev/disk/by-id/usb-Micron_ABCDEF1234-0:0-part2',
            uuid=self.uuid, device_serial=self.serial,
            backup_manifest=self.bak_manifest, record_ingest=record,
            writable_session=write_session or Window(),
            attest_read_only=identity or (lambda: (self.uuid, self.serial, True)),
            watchdog_verified=watchdog or (lambda: True))

    def test_two_way_transfer_and_separate_receipts(self):
        with patch('truepanel.cargo.supervised_bidirectional_batch._writable_identity') as check:
            outcome = self.invoke()
        self.assertEqual(outcome['state'], 'HOST_BIDIRECTIONAL_VERIFIED')
        self.assertEqual(len(outcome['transfers']), 2)
        self.assertTrue((self.usb / 'Export/alpha.bin').is_file())
        self.assertTrue((self.nas / 'Ingest/beta.bin').is_file())
        self.assertTrue(self.bak_manifest.is_file())
        self.assertEqual(len(list(self.ingest_root.glob('*.json'))), 1)
        self.assertEqual(check.call_count, 4)

    def test_reapproval_reconciles_without_recopy(self):
        with patch('truepanel.cargo.supervised_bidirectional_batch._writable_identity'):
            self.invoke()
        new_scope = CargoScope('spare-lab', self.uuid, self.serial,
            inspect_bidirectional(nas_root=self.nas, usb_root=self.usb,
                                  entries=self.entries, recover_verified=True))
        self.scope = new_scope
        with patch('truepanel.cargo.supervised_bidirectional_batch._writable_identity'):
            second = self.invoke()
        self.assertTrue(all(not x['new_transfer'] for x in second['transfers']))
        self.assertEqual(len(list(self.ingest_root.glob('*.json'))), 1)

    def test_no_watchdog_refuses_before_burning_approval(self):
        bridge = Bridge(self.scope)
        with self.assertRaisesRegex(BackupExecutionError, 'watchdog'):
            self.invoke(bridge=bridge, watchdog=lambda: False)
        self.assertEqual(bridge.calls, 0)
        self.assertFalse((self.usb / 'Export/alpha.bin').exists())

    def test_identity_swap_refuses_before_burning_approval(self):
        bridge = Bridge(self.scope)
        with self.assertRaisesRegex(BackupExecutionError, 'hardware qualified'):
            self.invoke(bridge=bridge, identity=lambda: (self.uuid, 'UNSAFE999', True))
        self.assertEqual(bridge.calls, 0)

    def test_conflicting_destination_refuses_pre_authorization(self):
        (self.usb / 'Export').mkdir()
        (self.usb / 'Export/alpha.bin').write_text('malicious collision')
        bridge = Bridge(self.scope)
        with self.assertRaises(BackupExecutionError):
            self.invoke(bridge=bridge)
        self.assertEqual(bridge.calls, 0)
        self.assertEqual((self.usb / 'Export/alpha.bin').read_text(), 'malicious collision')

    def test_wrong_confirmation_digest_refuses_write_window(self):
        bridge = Bridge(self.scope)
        bridge.scope = CargoScope('spare-lab', self.uuid, self.serial, self.scope.actions)
        window = Window()
        with self.assertRaisesRegex(BackupExecutionError, 'approval digest mismatch'):
            self.invoke(bridge=bridge, write_session=window)
        self.assertFalse(window.entered)

    def test_second_file_change_refuses_and_restores_context(self):
        window = Window()
        # Collision on first file occurs during write, after bridge consumption.
        from truepanel.cargo.supervised_bidirectional_batch import transfer_one_approved as original
        def collide(*, nas_root, usb_root, action, device_serial):
            if action.relative_path == 'Export/alpha.bin':
                result = original(nas_root=nas_root, usb_root=usb_root, action=action,
                                  device_serial=device_serial)
                (self.usb / 'Ingest/beta.bin').write_bytes(b'changed')
                return result
            return original(nas_root=nas_root, usb_root=usb_root, action=action,
                            device_serial=device_serial)
        with patch('truepanel.cargo.supervised_bidirectional_batch._writable_identity'), \
             patch('truepanel.cargo.supervised_bidirectional_batch.transfer_one_approved', side_effect=collide):
            with self.assertRaises(BackupExecutionError):
                self.invoke(write_session=window)
        self.assertTrue(window.exited)
        self.assertTrue((self.usb / 'Export/alpha.bin').exists())
        self.assertFalse((self.nas / 'Ingest/beta.bin').exists())

    def test_symlink_destination_refused(self):
        (self.usb / 'Export').symlink_to(self.nas / 'Export', target_is_directory=True)
        bridge = Bridge(self.scope)
        with self.assertRaises(BackupExecutionError):
            self.invoke(bridge=bridge)
        self.assertEqual(bridge.calls, 0)

    def test_replay_bridge_rejected(self):
        bridge = Bridge(self.scope)
        with patch('truepanel.cargo.supervised_bidirectional_batch._writable_identity'):
            self.invoke(bridge=bridge)
            with self.assertRaisesRegex(BackupExecutionError, 'already consumed'):
                self.invoke(bridge=bridge)

    def test_read_only_restoration_failure_never_records_receipts(self):
        calls = [0]
        def identity():
            calls[0] += 1
            if calls[0] > 1:
                return self.uuid, self.serial, False
            return self.uuid, self.serial, True
        window = Window()
        with patch('truepanel.cargo.supervised_bidirectional_batch._writable_identity'):
            with self.assertRaisesRegex(BackupExecutionError, 'returned to verified read-only'):
                self.invoke(identity=identity, write_session=window)
        self.assertTrue(window.exited)
        self.assertFalse(self.bak_manifest.exists())
        self.assertEqual(list(self.ingest_root.glob('*.json')), [])

    def test_watchdog_loss_during_batch_aborts_with_context_exit(self):
        calls = [0]
        def watchdog():
            calls[0] += 1
            return calls[0] < 3
        window = Window()
        with patch('truepanel.cargo.supervised_bidirectional_batch._writable_identity'):
            with self.assertRaisesRegex(BackupExecutionError, 'watchdog lost'):
                self.invoke(watchdog=watchdog, write_session=window)
        self.assertTrue(window.exited)
        self.assertFalse(self.bak_manifest.exists())

    def test_no_freeform_cli(self):
        from truepanel.cargo import supervised_bidirectional_batch as module
        self.assertFalse(hasattr(module, 'main'))


if __name__ == '__main__':
    unittest.main()
