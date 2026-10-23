"""No-hardware unittest qualification for real host approval and direction scope."""
import tempfile
import unittest
import time
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from truepanel.cargo.backup_executor import BackupExecutionError
from truepanel.cargo.bidirectional_host_scope import (
    CargoAction, CargoScope, HostBidirectionalApprovalSession,
    inspect_bidirectional,
)
from truepanel.cargo.copy_button import CopyButtonConfirmation, LoadmasterCopyButtonGate
from truepanel.host.loadmaster_copy_button import LoadmasterCopyButtonService
from truepanel.host.loadmaster_session_bridge import LoadmasterHostSessionBridge
from truepanel.hardware.fintek_gpio import FintekCopyButtonReader


class FintekFakePortIO:
    """Model real selector/register interface; refuse GPIO data writes."""
    def __init__(self, *, direction=0x0C, chip=0x1007):
        self.sio_index = 0
        self.runtime_index = 0
        self.direction = direction
        self.chip = chip
        self.level = 0x7F
        self.writes = []

    def write8(self, port, value):
        self.writes.append((port, value))
        if port == 0x2E:
            self.sio_index = value
        elif port == 0x0605:
            self.runtime_index = value
        elif port == 0x2F and self.sio_index == 0x07:
            pass
        else:
            raise AssertionError('unexpected GPIO data or configuration write')

    def read8(self, port):
        regs = {0x20:self.chip >> 8, 0x21:self.chip & 255,
                0x23:0x19, 0x24:0x34, 0x30:1, 0x60:6, 0x61:0}
        if port == 0x2F:
            return regs.get(self.sio_index, 0)
        if port == 0x0606:
            return {0x80:self.direction, 0x82:self.level}.get(self.runtime_index, 0)
        raise AssertionError('unexpected read')

    def close(self):
        pass


class FakeReader:
    level = 1
    def read_level(self):
        return self.level
    def close(self):
        pass


class DirectionBoundTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='lm-physical-plan-')
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.nas = self.root/'nas'
        self.usb = self.root/'usb'
        self.nas.mkdir()
        self.usb.mkdir()
        (self.nas/'Export').mkdir()
        (self.usb/'Import').mkdir()
        (self.nas/'Export'/'ep.mkv').write_bytes(b'A'*4096)
        (self.usb/'Import'/'ep.mkv').write_bytes(b'B'*5120)
        self.entries = (('NAS_TO_USB', 'Export/ep.mkv'),
                        ('USB_TO_NAS', 'Import/ep.mkv'))
        self.actions = inspect_bidirectional(nas_root=self.nas, usb_root=self.usb,
                                             entries=self.entries)
        self.scope = CargoScope('spare-lab', '6ADA-80D5', '2532EA8D421A', self.actions)
        self.journal = self.root/'journal'
        self.journal.mkdir(mode=0o700)

    def build_bridge(self, *, clock=time.monotonic):
        reader = FakeReader()
        service = LoadmasterCopyButtonService(
            reader=reader,
            gate=LoadmasterCopyButtonGate(read_level=reader.read_level,clock=clock,
                                          debounce_seconds=.01, confirmation_window_seconds=.25),
            poll_seconds=.002)
        session = HostBidirectionalApprovalSession(
            fresh_actions=lambda: inspect_bidirectional(
                nas_root=self.nas, usb_root=self.usb, entries=self.entries),
            attest_identity=lambda: (self.scope.cartridge_uuid, self.scope.device_serial, True),
            clock=clock)
        bridge = LoadmasterHostSessionBridge(service=service, session=session)
        self.addCleanup(bridge.disarm)
        self.addCleanup(service.stop)
        return reader, service, bridge

    def test_real_fintek_reader_register_contract(self):
        io = FintekFakePortIO()
        reader = FintekCopyButtonReader(io=io)
        self.assertEqual(reader.read_level(), 1)
        io.level = 0x5F
        self.assertEqual(reader.read_level(), 0)
        self.assertNotIn(0x0606, [port for port, _ in io.writes])
        reader.close()

    def test_fintek_rejects_output_direction(self):
        with self.assertRaisesRegex(RuntimeError, 'input'):
            FintekCopyButtonReader(io=FintekFakePortIO(direction=0x2C))

    def test_fintek_rejects_wrong_chip(self):
        with self.assertRaisesRegex(RuntimeError, 'chip id'):
            FintekCopyButtonReader(io=FintekFakePortIO(chip=0x1234))

    def test_directions_are_preserved(self):
        self.assertEqual([a.direction for a in self.actions], ['NAS_TO_USB','USB_TO_NAS'])

    def test_direction_flip_changes_digest(self):
        reversed_scope = replace(self.scope, actions=(replace(self.actions[0],direction='USB_TO_NAS'),
                                                      self.actions[1]))
        self.assertNotEqual(self.scope.digest, reversed_scope.digest)

    def test_serial_change_changes_digest(self):
        self.assertNotEqual(self.scope.digest, replace(self.scope, device_serial='2532EA8D3DC7').digest)

    def test_uuid_change_changes_digest(self):
        self.assertNotEqual(self.scope.digest, replace(self.scope, cartridge_uuid='6988-53EB').digest)

    def test_duplicate_cross_direction_rejected(self):
        with self.assertRaisesRegex(BackupExecutionError, 'duplicate'):
            inspect_bidirectional(nas_root=self.nas, usb_root=self.usb,
                                  entries=(self.entries[0],self.entries[0]))

    def test_existing_destination_no_overwrite(self):
        destination = self.usb/'Export'/'ep.mkv'
        destination.parent.mkdir(exist_ok=True)
        destination.write_bytes(b'preserve')
        with self.assertRaisesRegex(BackupExecutionError, 'occupied'):
            inspect_bidirectional(nas_root=self.nas, usb_root=self.usb,entries=self.entries)
        self.assertEqual(destination.read_bytes(), b'preserve')

    def test_recovery_verified_existing_copy(self):
        destination = self.usb/'Export'/'ep.mkv'
        destination.parent.mkdir(exist_ok=True)
        destination.write_bytes((self.nas/'Export'/'ep.mkv').read_bytes())
        actions = inspect_bidirectional(nas_root=self.nas,usb_root=self.usb,
                                        entries=self.entries,recover_verified=True)
        self.assertEqual(actions,self.actions)

    def test_recovery_conflict_rejected(self):
        destination = self.usb/'Export'/'ep.mkv'
        destination.parent.mkdir(exist_ok=True)
        destination.write_bytes(b'conflict')
        with self.assertRaisesRegex(BackupExecutionError, 'conflict'):
            inspect_bidirectional(nas_root=self.nas,usb_root=self.usb,
                                  entries=self.entries,recover_verified=True)
        self.assertEqual(destination.read_bytes(), b'conflict')

    def test_symlinked_source_rejected(self):
        link = self.nas/'Export'/'link.mkv'
        link.symlink_to(self.nas/'Export'/'ep.mkv')
        with self.assertRaisesRegex(BackupExecutionError, 'symlink'):
            inspect_bidirectional(nas_root=self.nas,usb_root=self.usb,
                                  entries=(('NAS_TO_USB','Export/link.mkv'),))

    def test_symlinked_destination_rejected(self):
        (self.nas/'Import').symlink_to(self.nas/'Export',target_is_directory=True)
        with self.assertRaisesRegex(BackupExecutionError, 'symlink'):
            inspect_bidirectional(nas_root=self.nas,usb_root=self.usb,entries=self.entries)

    def test_invalid_direction_rejected(self):
        with self.assertRaises(BackupExecutionError):
            inspect_bidirectional(nas_root=self.nas,usb_root=self.usb,
                                  entries=(('USB_DELETE','Export/ep.mkv'),))

    def test_physical_execution_hard_disabled(self):
        session = HostBidirectionalApprovalSession(fresh_actions=lambda:self.actions,
            attest_identity=lambda: (self.scope.cartridge_uuid,self.scope.device_serial,True))
        with self.assertRaisesRegex(BackupExecutionError, 'NOT_QUALIFIED'):
            session.execute_physical()

    def test_fresh_nonce_gives_distinct_digest_for_resumption(self):
        retry = replace(self.scope, attempt_nonce='b'*32)
        self.assertNotEqual(retry.digest, self.scope.digest)
        self.assertEqual(retry.actions, self.scope.actions)

    def test_bad_attempt_nonce_rejected(self):
        with self.assertRaisesRegex(BackupExecutionError, 'nonce'):
            replace(self.scope, attempt_nonce='not-a-valid-attempt').digest

    def test_missing_identity_check_fails_closed(self):
        with self.assertRaises(TypeError):
            HostBidirectionalApprovalSession(fresh_actions=lambda: self.actions)

    def test_identity_mismatch_refuses_arm(self):
        reader = FakeReader()
        service = LoadmasterCopyButtonService(reader=reader)
        session = HostBidirectionalApprovalSession(
            fresh_actions=lambda: self.actions,
            attest_identity=lambda: ('6988-53EB','2532EA8D3DC7',True))
        bridge = LoadmasterHostSessionBridge(service=service, session=session)
        with self.assertRaisesRegex(BackupExecutionError, 'identity'):
            bridge.prepare_and_arm((self.scope,self.journal))
        self.assertFalse(list(self.journal.glob('*.consumed')))

    def test_real_service_bridge_consumes_direction_bound_digest(self):
        reader, service, bridge = self.build_bridge()
        service.start()
        armed = bridge.prepare_and_arm((self.scope,self.journal))
        self.assertEqual(armed['plan_digest'],self.scope.digest)
        time.sleep(.035)
        reader.level = 0
        time.sleep(.09)
        reader.level = 1
        self.assertTrue(bridge.confirmed)
        evidence = bridge.consume_read_only()
        self.assertEqual(evidence['plan_digest'],self.scope.digest)
        self.assertFalse(evidence['physical_execution_enabled'])
        self.assertEqual(len(list(self.journal.glob('*.consumed'))),1)
        with self.assertRaises(BackupExecutionError):
            bridge.consume_read_only()

    def test_change_after_arming_refused(self):
        reader, service, bridge = self.build_bridge()
        bridge.prepare_and_arm((self.scope,self.journal))
        (self.usb/'Import'/'ep.mkv').write_bytes(b'MODIFIED')
        # Manually driving callback is allowed in test ONLY; no physical evidence
        service.on_confirmation(CopyButtonConfirmation(
            cartridge_id=self.scope.cartridge_id,
            cartridge_uuid=self.scope.cartridge_uuid,
            device_serial=self.scope.device_serial,
            plan_digest=self.scope.digest,
            confirmed_at_monotonic=time.monotonic()))
        with self.assertRaisesRegex(BackupExecutionError,'changed'):
            bridge.consume_read_only()
        self.assertFalse(list(self.journal.glob('*.consumed')))

    def test_cartridge_change_after_press_blocks_consumption(self):
        observed = [('6ADA-80D5','2532EA8D421A',True)]
        reader = FakeReader()
        service = LoadmasterCopyButtonService(reader=reader)
        session = HostBidirectionalApprovalSession(
            fresh_actions=lambda: self.actions,
            attest_identity=lambda: observed[0])
        bridge = LoadmasterHostSessionBridge(service=service, session=session)
        bridge.prepare_and_arm((self.scope,self.journal))
        service.on_confirmation(CopyButtonConfirmation(
            cartridge_id=self.scope.cartridge_id,
            cartridge_uuid=self.scope.cartridge_uuid,
            device_serial=self.scope.device_serial,
            plan_digest=self.scope.digest,
            confirmed_at_monotonic=time.monotonic()))
        observed[0] = ('6988-53EB','2532EA8D3DC7',True)
        with self.assertRaisesRegex(BackupExecutionError,'identity'):
            bridge.consume_read_only()
        self.assertFalse(list(self.journal.glob('*.consumed')))
        bridge.disarm()

    def test_wrong_digest_never_accepted(self):
        _, service, bridge = self.build_bridge()
        bridge.prepare_and_arm((self.scope,self.journal))
        service.on_confirmation(CopyButtonConfirmation(
            cartridge_id=self.scope.cartridge_id,
            cartridge_uuid=self.scope.cartridge_uuid,
            device_serial=self.scope.device_serial,
            plan_digest='0'*64, confirmed_at_monotonic=time.monotonic()))
        with self.assertRaises(BackupExecutionError):
            bridge.consume_read_only()
        self.assertFalse(list(self.journal.glob('*.consumed')))

    def test_same_digest_cannot_be_reused_across_restart(self):
        _, service, bridge = self.build_bridge()
        bridge.prepare_and_arm((self.scope,self.journal))
        service.on_confirmation(CopyButtonConfirmation(
            cartridge_id=self.scope.cartridge_id,
            cartridge_uuid=self.scope.cartridge_uuid,
            device_serial=self.scope.device_serial,
            plan_digest=self.scope.digest,confirmed_at_monotonic=time.monotonic()))
        bridge.consume_read_only()
        _, service2, bridge2 = self.build_bridge()
        bridge2.prepare_and_arm((self.scope,self.journal))
        service2.on_confirmation(CopyButtonConfirmation(
            cartridge_id=self.scope.cartridge_id,
            cartridge_uuid=self.scope.cartridge_uuid,
            device_serial=self.scope.device_serial,
            plan_digest=self.scope.digest,confirmed_at_monotonic=time.monotonic()))
        with self.assertRaisesRegex(BackupExecutionError,'already consumed'):
            bridge2.consume_read_only()
        self.assertEqual(len(list(self.journal.glob('*.consumed'))),1)


if __name__ == '__main__':
    unittest.main()
