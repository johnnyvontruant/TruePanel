"""No hardware used: fake GPIO levels with the real TruePanel gate class."""
import hashlib
import os
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from truepanel.cargo.copy_button import LoadmasterCopyButtonGate, LoadmasterPhysicalPreflight
from truepanel.cargo.durable_batch_lab import (
    BatchError, batch_digest, execute_batch, plan_batch, read_receipt,
    reapprove_batch, _lock_journal,
)
from truepanel.cargo.resumable_rsync_lab import Intent, LabError, InterruptedTransfer


class Clock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now

    def tick(self, sec):
        self.now += sec


class DurableBatchLabTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='lm-batch-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / '.loadmaster-lab-only').write_text('LAB_ONLY\n')
        self.nas = self.root / 'nas'
        self.usb = self.root / 'usb'
        self.nas.mkdir()
        self.usb.mkdir()
        (self.nas / 'outgoing.mkv').write_bytes(os.urandom(64 * 1024))
        (self.usb / 'incoming.mkv').write_bytes(os.urandom(32 * 1024))
        self.clock = Clock()

    def batch(self):
        return plan_batch(
            self.root, cartridge_id='SPARE-TEST', cartridge_uuid='6ADA-80D5',
            device_serial='2532EA8D421A',
            entries=[('NAS_TO_USB', 'outgoing.mkv'), ('USB_TO_NAS', 'incoming.mkv')],
        )

    def event(self, batch):
        state = {'level': 1}
        gate = LoadmasterCopyButtonGate(read_level=lambda: state['level'],
                                        clock=self.clock)
        preflight = LoadmasterPhysicalPreflight(
            cartridge_id=batch.cartridge_id, cartridge_uuid=batch.cartridge_uuid,
            device_serial=batch.device_serial, plan_state='READY',
            backup_files=len(batch.actions),
            backup_bytes=sum(a.size for a in batch.actions),
            baseline_verified=True, identity_verified=True, backlog_verified=True,
            plan_digest=batch_digest(batch), generated_at_monotonic=self.clock(),
        )
        gate.arm(preflight)
        self.assertIsNone(gate.poll())
        self.clock.tick(.09)
        self.assertIsNone(gate.poll())
        state['level'] = 0
        self.assertIsNone(gate.poll())
        self.clock.tick(.09)
        confirmation = gate.poll()
        self.assertIsNotNone(confirmation)
        return confirmation

    def test_two_way_batch_and_durable_receipt(self):
        b = self.batch()
        r = execute_batch(self.root, b, self.event(b), clock=self.clock)
        self.assertEqual(r['state'], 'COMPLETE')
        self.assertEqual(len(r['verified']), 2)
        self.assertFalse(r['incomplete'])
        self.assertEqual((self.usb / 'outgoing.mkv').read_bytes(),
                         (self.nas / 'outgoing.mkv').read_bytes())
        self.assertEqual((self.nas / 'incoming.mkv').read_bytes(),
                         (self.usb / 'incoming.mkv').read_bytes())
        self.assertEqual(read_receipt(self.root, b)['state'], 'COMPLETE')

    def test_approval_replay_refused_after_reopen(self):
        b = self.batch()
        confirmation = self.event(b)
        execute_batch(self.root, b, confirmation, clock=self.clock)
        with self.assertRaisesRegex(BatchError, 'replay'):
            execute_batch(self.root, b, confirmation, clock=self.clock)
        self.assertEqual(read_receipt(self.root, b)['state'], 'COMPLETE')

    def test_bad_cartridge_uuid(self):
        b = self.batch()
        confirmation = self.event(b)
        wrong = replace(b, cartridge_uuid='NOT-THE-SPARE')
        with self.assertRaisesRegex(BatchError, 'match'):
            execute_batch(self.root, wrong, confirmation, clock=self.clock)
        self.assertIsNone(read_receipt(self.root, wrong))

    def test_bad_cartridge_serial(self):
        b = self.batch()
        confirmation = self.event(b)
        with self.assertRaisesRegex(BatchError, 'match'):
            execute_batch(self.root, replace(b, device_serial='WRONG'),
                          confirmation, clock=self.clock)

    def test_modified_action_after_button_press(self):
        b = self.batch()
        confirmation = self.event(b)
        other = replace(b, actions=(replace(b.actions[0], sha256='0'*64), b.actions[1]))
        with self.assertRaisesRegex(BatchError, 'match'):
            execute_batch(self.root, other, confirmation, clock=self.clock)

    def test_expired_confirmation(self):
        b = self.batch()
        confirmation = self.event(b)
        self.clock.tick(31)
        with self.assertRaisesRegex(BatchError, 'expired'):
            execute_batch(self.root, b, confirmation, clock=self.clock)

    def test_future_confirmation_refused(self):
        b = self.batch()
        confirmation = self.event(b)
        self.clock.tick(-1)
        with self.assertRaisesRegex(BatchError, 'future'):
            execute_batch(self.root, b, confirmation, clock=self.clock)

    def test_missing_confirmation(self):
        b = self.batch()
        with self.assertRaisesRegex(BatchError, 'required'):
            execute_batch(self.root, b, None, clock=self.clock)
        self.assertFalse((self.usb / 'outgoing.mkv').exists())

    def test_changed_source_never_published(self):
        b = self.batch()
        event = self.event(b)
        (self.nas / 'outgoing.mkv').write_bytes(b'new version')
        with self.assertRaisesRegex(LabError, 'source differs'):
            execute_batch(self.root, b, event, clock=self.clock)
        self.assertEqual(read_receipt(self.root, b)['state'], 'INTERRUPTED')
        self.assertFalse((self.usb / 'outgoing.mkv').exists())

    def test_destination_collision_does_not_overwrite(self):
        b = self.batch()
        event = self.event(b)
        (self.usb / 'outgoing.mkv').write_bytes(b'precious existing file')
        with self.assertRaisesRegex(LabError, 'never overwrite'):
            execute_batch(self.root, b, event, clock=self.clock)
        self.assertEqual((self.usb / 'outgoing.mkv').read_bytes(), b'precious existing file')

    def test_new_approval_recovers_after_completed_one_and_interrupted_second(self):
        (self.usb / 'incoming.mkv').write_bytes(os.urandom(8*1024*1024))
        b = self.batch()
        with self.assertRaises(InterruptedTransfer):
            execute_batch(self.root, b, self.event(b), clock=self.clock,
                          interrupt_index=1, interrupt_after=1.2, bwlimit_kib=512)
        old = read_receipt(self.root, b)
        self.assertEqual(old['state'], 'INTERRUPTED')
        self.assertEqual(len(old['verified']), 1)
        first_before = (self.usb / 'outgoing.mkv').read_bytes()
        self.assertFalse((self.nas / 'incoming.mkv').exists())
        with self.assertRaisesRegex(BatchError, 'replay'):
            execute_batch(self.root, b, self.event(b), clock=self.clock)
        b2 = reapprove_batch(b)
        self.assertNotEqual(batch_digest(b), batch_digest(b2))
        r = execute_batch(self.root, b2, self.event(b2), clock=self.clock)
        self.assertEqual(r['state'], 'COMPLETE')
        self.assertEqual(r['verified'][0]['state'], 'PUBLISHED_ALREADY_VERIFIED')
        self.assertEqual((self.usb / 'outgoing.mkv').read_bytes(), first_before)
        self.assertEqual((self.nas / 'incoming.mkv').read_bytes(),
                         (self.usb / 'incoming.mkv').read_bytes())
        self.assertEqual(read_receipt(self.root, b)['state'], 'INTERRUPTED')

    def test_simulated_abrupt_process_exit_recovers_without_reusing_approval(self):
        from truepanel.cargo import durable_batch_lab as code
        b = self.batch()
        actual = code.transfer
        calls = {'n': 0}
        def crash_after_first(*args, **kwargs):
            calls['n'] += 1
            if calls['n'] == 2:
                raise SystemExit('simulated SIGKILL boundary before next file')
            return actual(*args, **kwargs)
        with patch.object(code, 'transfer', side_effect=crash_after_first):
            with self.assertRaises(SystemExit):
                execute_batch(self.root, b, self.event(b), clock=self.clock)
        receipt = read_receipt(self.root, b)
        self.assertEqual(receipt['state'], 'IN_PROGRESS')
        self.assertEqual(len(receipt['verified']), 1)
        b2 = reapprove_batch(b)
        result = execute_batch(self.root, b2, self.event(b2), clock=self.clock)
        self.assertEqual(result['verified'][0]['state'], 'PUBLISHED_ALREADY_VERIFIED')
        self.assertEqual(result['state'], 'COMPLETE')

    def test_crash_after_publish_before_receipt_update(self):
        from truepanel.cargo import durable_batch_lab as code
        b = self.batch()
        actual = code._durable_update
        calls = {'count': 0}
        def crash_before_receipt(*args, **kwargs):
            calls['count'] += 1
            if calls['count'] == 1:
                # The transfer has already fsynced and published the first file.
                raise SystemExit('crash after publish but before journal update')
            return actual(*args, **kwargs)
        with patch.object(code, '_durable_update', side_effect=crash_before_receipt):
            with self.assertRaises(SystemExit):
                execute_batch(self.root, b, self.event(b), clock=self.clock)
        self.assertTrue((self.usb/'outgoing.mkv').is_file())
        self.assertEqual(read_receipt(self.root, b)['state'], 'CONSUMED')
        with self.assertRaisesRegex(BatchError, 'replay'):
            execute_batch(self.root, b, self.event(b), clock=self.clock)
        b2 = reapprove_batch(b)
        result = execute_batch(self.root, b2, self.event(b2), clock=self.clock)
        self.assertEqual(result['state'], 'COMPLETE')
        self.assertEqual(result['verified'][0]['state'], 'PUBLISHED_ALREADY_VERIFIED')

    def test_symlinked_journal_refused(self):
        outside = self.root/'outside-journal'
        outside.mkdir()
        (self.root/'.loadmaster-batch-lab-journal').symlink_to(outside, target_is_directory=True)
        b = self.batch()
        with self.assertRaisesRegex(LabError, 'symlink'):
            execute_batch(self.root, b, self.event(b), clock=self.clock)
        self.assertEqual(list(outside.iterdir()), [])

    def test_symlinked_approval_receipt_refused(self):
        b = self.batch()
        from truepanel.cargo import durable_batch_lab as code
        journal = code._journal(self.root)
        external = self.root/'fake-approval'
        external.write_text('keep untouched')
        (journal/(batch_digest(b)+'.json')).symlink_to(external)
        with self.assertRaises(LabError):
            execute_batch(self.root, b, self.event(b), clock=self.clock)
        self.assertEqual(external.read_text(), 'keep untouched')

    def test_no_side_effects_from_failed_validation(self):
        b = self.batch()
        bad = replace(b, device_serial='swapped device')
        with self.assertRaises(BatchError):
            execute_batch(self.root, bad, self.event(b), clock=self.clock)
        self.assertFalse((self.root/'.loadmaster-batch-lab-journal').exists())
        self.assertFalse((self.usb/'outgoing.mkv').exists())

    def test_real_process_kill_after_publish_can_reconcile(self):
        import json
        import signal
        import subprocess
        import sys
        b = self.batch()
        payload = {
            'cartridge_id': b.cartridge_id,
            'cartridge_uuid': b.cartridge_uuid,
            'device_serial': b.device_serial,
            'attempt_nonce': b.attempt_nonce,
            'actions': [dict(direction=a.direction, relative=a.relative,
                             size=a.size, sha256=a.sha256) for a in b.actions],
        }
        child = r"""
import json, os, signal, sys, time
from pathlib import Path
from truepanel.cargo.copy_button import LoadmasterCopyButtonGate, LoadmasterPhysicalPreflight
from truepanel.cargo.resumable_rsync_lab import Intent
from truepanel.cargo import durable_batch_lab as d
payload = json.loads(sys.argv[2])
b = d.Batch(payload['cartridge_id'], payload['cartridge_uuid'],
            payload['device_serial'],
            tuple(Intent(**a) for a in payload['actions']), payload['attempt_nonce'])
level = [1]
gate = LoadmasterCopyButtonGate(read_level=lambda: level[0])
p = LoadmasterPhysicalPreflight(
    cartridge_id=b.cartridge_id, cartridge_uuid=b.cartridge_uuid,
    device_serial=b.device_serial, plan_state='READY',
    backup_files=len(b.actions), backup_bytes=sum(a.size for a in b.actions),
    baseline_verified=True, identity_verified=True, backlog_verified=True,
    plan_digest=d.batch_digest(b), generated_at_monotonic=time.monotonic())
gate.arm(p)
gate.poll(); time.sleep(.085); gate.poll()
level[0] = 0; gate.poll(); time.sleep(.085)
confirmation = gate.poll()
assert confirmation is not None
# First file is published before its receipt is updated.
def kill_on_first_update(*_args, **_kwargs):
    os.kill(os.getpid(), signal.SIGKILL)
d._durable_update = kill_on_first_update
d.execute_batch(Path(sys.argv[1]), b, confirmation)
"""
        cp = subprocess.run([sys.executable, '-c', child, str(self.root),
                             json.dumps(payload)], timeout=20,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.assertEqual(cp.returncode, -signal.SIGKILL, cp.stderr)
        self.assertEqual(read_receipt(self.root, b)['state'], 'CONSUMED')
        self.assertTrue((self.usb/'outgoing.mkv').is_file())
        b2 = reapprove_batch(b)
        result = execute_batch(self.root, b2, self.event(b2), clock=self.clock)
        self.assertEqual(result['state'], 'COMPLETE')
        self.assertEqual(result['verified'][0]['state'], 'PUBLISHED_ALREADY_VERIFIED')

    def test_approval_recorded_durably_before_first_copy(self):
        from truepanel.cargo import durable_batch_lab as code
        b = self.batch()
        actual = code.transfer
        calls = {'count': 0}
        def inspect_then_copy(*args, **kwargs):
            if calls['count'] == 0:
                self.assertEqual(read_receipt(self.root, b)['state'], 'CONSUMED')
            calls['count'] += 1
            return actual(*args, **kwargs)
        with patch.object(code, 'transfer', side_effect=inspect_then_copy):
            execute_batch(self.root, b, self.event(b), clock=self.clock)

    def test_concurrent_attempt_locked(self):
        b = self.batch()
        event = self.event(b)
        with _lock_journal(self.root):
            with self.assertRaisesRegex(BatchError, 'locked'):
                execute_batch(self.root, b, event, clock=self.clock)
        self.assertIsNone(read_receipt(self.root, b))

    def test_duplicate_path_rejected(self):
        b = self.batch()
        invalid = replace(b, actions=(b.actions[0], b.actions[0]))
        with self.assertRaisesRegex(BatchError, 'duplicate'):
            batch_digest(invalid)

    def test_cross_direction_conflict_rejected(self):
        b = self.batch()
        invalid = replace(b, actions=(b.actions[0],
                                  replace(b.actions[1], relative=b.actions[0].relative)))
        with self.assertRaisesRegex(BatchError, 'conflicting'):
            batch_digest(invalid)

    def test_no_escape_from_disposable_lab(self):
        b = self.batch()
        with self.assertRaises(LabError):
            execute_batch(Path('/mnt'), b, self.event(b), clock=self.clock)

    def test_bad_receipt_refused(self):
        b = self.batch()
        execute_batch(self.root, b, self.event(b), clock=self.clock)
        record = self.root/'.loadmaster-batch-lab-journal'/(batch_digest(b)+'.json')
        record.write_text('{"schema_version":1,"digest":"WRONG"}')
        with self.assertRaisesRegex(BatchError, 'mismatch'):
            read_receipt(self.root, b)

    def test_reapproval_does_not_change_source_identity(self):
        b = self.batch()
        b2 = reapprove_batch(b)
        self.assertEqual(b.actions, b2.actions)
        self.assertEqual((b.cartridge_id, b.cartridge_uuid, b.device_serial),
                         (b2.cartridge_id, b2.cartridge_uuid, b2.device_serial))


if __name__ == '__main__':
    unittest.main()
