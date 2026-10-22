"""Disposable integration tests for the staged supervised USB actuator."""
import hashlib
import json
import tempfile
import unittest
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from truepanel.cargo.backup_coordinator import canonical_plan_digest
from truepanel.cargo.backup_executor import BackupExecutionError
from truepanel.cargo.physical_backup_actuator import execute_supervised_single_file, recover_read_only_evidence


class SimulatedBridge:
    def __init__(self, approval):
        self.approval = approval
        self.consumed = 0

    def consume_read_only(self):
        self.consumed += 1
        return self.approval


class PhysicalActuatorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.mount = self.root / 'mount'
        self.mount.mkdir()
        self.nas = self.root / 'nas'
        self.nas.mkdir()
        (self.nas / 'Show').mkdir()
        self.usb = self.mount / 'TV N-Z'
        self.usb.mkdir()
        self.source = self.nas / 'Show' / '1x03.mkv'
        self.source.write_bytes(b'one-episode' * 1000)
        self.destination = self.usb / 'Show' / '1x03.mkv'
        self.manifest = self.root / 'manifest.json'
        self.registry = self.root / 'registry.json'
        self.plan = {
            'schema_version': 1, 'scope': 'durable_backlog', 'read_only': True,
            'delete_policy': 'never', 'state': 'READY', 'conflicts': [],
            'cartridge': {'id': 'tv-n-z'}, 'nas_root': str(self.nas),
            'usb_root': str(self.usb),
            'summary': {'scoped_items': 1, 'backup_files': 1,
                        'backup_bytes': self.source.stat().st_size,
                        'conflicts': 0, 'ingest_files': 0},
            'actions': [{'direction': 'NAS_TO_USB', 'relative_path': 'Show/1x03.mkv',
                         'size_bytes': self.source.stat().st_size}]}
        digest = canonical_plan_digest(self.plan)
        self.inspection = {
            'state': 'READ_ONLY_TRANSACTION_ACCEPTED', 'mount_read_only': True,
            'destination_absent': True, 'source': str(self.source),
            'destination': str(self.destination), 'uuid': '6988-53EB',
            'source_sha256': hashlib.sha256(self.source.read_bytes()).hexdigest(),
            'cartridge_id': 'tv-n-z', 'device_serial_registered': True,
            'relative_path': 'Show/1x03.mkv', 'size_bytes': self.source.stat().st_size, 'plan_digest': digest,
        }
        self.bridge = SimulatedBridge({
            'state': 'HOST_APPROVAL_EVIDENCE_ONLY', 'cartridge_id': 'tv-n-z',
            'plan_digest': digest, 'executed': False,
            'backup_authorized': False, 'physical_execution_enabled': False,
        })
        cartridge = SimpleNamespace(
            cartridge_id='tv-n-z', source_prefix=self.nas,
            usb_relative_path=Path('TV N-Z'), uuid='6988-53EB',
            allow_ingest=False, allow_backup=False, delete_policy='never',
            device_serial='2532EA8D3DC7')
        self.registry_patch = patch(
            'truepanel.cargo.physical_backup_actuator.load_cartridge_registry',
            return_value=[cartridge])
        self.mount_patch = patch(
            'truepanel.cargo.physical_backup_actuator._writable_identity')
        self.registry_patch.start()
        self.mount_patch.start()
        self.addCleanup(self.registry_patch.stop)
        self.addCleanup(self.mount_patch.stop)

    def run_it(self, **overrides):
        options = {
            'plan': self.plan, 'inspection': self.inspection,
            'host_bridge': self.bridge, 'writable_session': nullcontext(),
            'registry': self.registry, 'mount': self.mount,
            'by_id': '/dev/disk/by-id/usb-Micron_CT8000X10SSD9_2532EA8D3DC7-0:0-part2',
            'manifest': self.manifest,
        }
        options.update(overrides)
        return execute_supervised_single_file(**options)

    def test_verified_copy_then_manifest(self):
        outcome = self.run_it()
        self.assertEqual(outcome['state'], 'PHYSICAL_BACKUP_VERIFIED')
        self.assertEqual(outcome['copy_state'], 'NEW_VERIFIED_COPY')
        self.assertEqual(self.destination.read_bytes(), self.source.read_bytes())
        self.assertEqual(len(json.loads(self.manifest.read_text())['items']), 1)
        self.assertEqual(self.bridge.consumed, 1)

    def test_existing_copy_only_reconciles_evidence(self):
        self.destination.parent.mkdir()
        self.destination.write_bytes(self.source.read_bytes())
        outcome = self.run_it()
        self.assertEqual(outcome['copy_state'], 'RECOVERED_VERIFIED_COPY')
        self.assertFalse(outcome['physical_copy'])

    def test_occupied_corrupt_destination_never_overwritten(self):
        self.destination.parent.mkdir()
        self.destination.write_bytes(b'original unrelated data')
        with self.assertRaisesRegex(BackupExecutionError, 'mismatch'):
            self.run_it()
        self.assertEqual(self.destination.read_bytes(), b'original unrelated data')
        self.assertFalse(self.manifest.exists())

    def test_wrong_approval_refused_before_copy(self):
        self.bridge.approval['plan_digest'] = '0' * 64
        with self.assertRaises(BackupExecutionError):
            self.run_it()
        self.assertFalse(self.destination.exists())

    def test_read_only_inspection_required(self):
        self.inspection['mount_read_only'] = False
        with self.assertRaises(BackupExecutionError):
            self.run_it()
        self.assertEqual(self.bridge.consumed, 0)

    def test_host_rw_context_required(self):
        with self.assertRaises(BackupExecutionError):
            self.run_it(writable_session=None)
        self.assertFalse(self.destination.exists())

    def recover(self):
        backlog = self.root / 'backlog.json'
        backlog.write_text(json.dumps({'items': [
            {'current_path': str(self.source),
             'size_bytes': self.source.stat().st_size}]}))
        with patch('truepanel.cargo.backup_executor.attest_cartridge_read_only'):
            return recover_read_only_evidence(
                registry=self.registry, backlog=backlog, mount=self.mount,
                by_id='/dev/disk/by-id/usb-Micron_CT8000X10SSD9_2532EA8D3DC7-0:0-part2',
                cartridge_id='tv-n-z', source=self.source,
                manifest=self.manifest)

    def test_read_only_crash_recovery_without_replay(self):
        self.run_it()
        self.manifest.unlink()
        result = self.recover()
        self.assertEqual(result['state'], 'READ_ONLY_EVIDENCE_RECONCILED')
        self.assertEqual(result['manifest_state'], 'EVIDENCE_RECORDED')
        self.assertFalse(result['physical_copy'])
        self.assertEqual(self.recover()['manifest_state'], 'ALREADY_RECORDED')

    def test_read_only_recovery_refuses_corruption(self):
        self.run_it()
        self.manifest.unlink()
        self.destination.write_bytes(b'corrupt and unrelated')
        with self.assertRaisesRegex(BackupExecutionError, 'mismatch'):
            self.recover()
        self.assertFalse(self.manifest.exists())

    def test_source_modified_since_inspection_no_manifest(self):
        self.source.write_bytes(b'changed bytes of different size')
        with self.assertRaises(BackupExecutionError):
            self.run_it()
        self.assertFalse(self.manifest.exists())

if __name__ == '__main__':
    unittest.main()


class WritableIdentityTests(unittest.TestCase):
    def setUp(self):
        self.mount = Path('/mnt/test')
        self.by_id = '/dev/disk/by-id/usb-Micron_CT8000X10SSD9_2532EA8D3DC7-0:0-part2'

    def invoke(self, mount_info, uuid='6988-53EB', real_id='/dev/sdi2'):
        from truepanel.cargo.physical_backup_actuator import _writable_identity
        from unittest.mock import patch
        def output(args, **kwargs):
            if args[0] == 'findmnt':
                return mount_info
            if args[0] == 'blkid':
                return uuid
            raise AssertionError('unexpected command')
        def realpath(path):
            return real_id if str(path) == self.by_id else str(path)
        with patch('truepanel.cargo.physical_backup_actuator.subprocess.check_output',
                   side_effect=output), patch(
                   'truepanel.cargo.physical_backup_actuator.os.path.realpath',
                   side_effect=realpath):
            _writable_identity(mount=self.mount, by_id=self.by_id, uuid='6988-53EB')

    def test_exact_rw_uuid_and_byid_accepted(self):
        self.invoke('/dev/sdi2 /mnt/test exfat rw,nosuid,nodev')

    def test_read_only_mount_rejected(self):
        with self.assertRaisesRegex(BackupExecutionError, 'writable'):
            self.invoke('/dev/sdi2 /mnt/test exfat ro,nosuid,nodev')

    def test_wrong_uuid_rejected(self):
        with self.assertRaisesRegex(BackupExecutionError, 'identity mismatch'):
            self.invoke('/dev/sdi2 /mnt/test exfat rw,nosuid', uuid='wrong')

    def test_wrong_device_link_rejected(self):
        with self.assertRaisesRegex(BackupExecutionError, 'identity mismatch'):
            self.invoke('/dev/sdi2 /mnt/test exfat rw', real_id='/dev/sdb2')

    def test_parent_mount_rejected(self):
        with self.assertRaisesRegex(BackupExecutionError, 'writable'):
            self.invoke('/dev/sdi2 /mnt exfat rw')
