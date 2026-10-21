"""Integration boundaries of the non-actuating transfer coordinator."""
import copy
import tempfile
import unittest
from pathlib import Path

from truepanel.cargo.backup_executor import BackupExecutionError
from truepanel.cargo.backup_coordinator import (
    canonical_plan_digest, execute_physical_plan, execute_sandbox_plan, plan_summary,
)


class CoordinatorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.nas = self.root / 'nas'
        self.usb = self.root / 'usb'
        self.nas.mkdir()
        self.usb.mkdir()
        (self.nas / 'Show').mkdir()
        self.content = b'episode-test' * 1000
        (self.nas / 'Show' / '1x03.mkv').write_bytes(self.content)
        self.plan = {
            'schema_version': 1, 'read_only': True, 'delete_policy': 'never',
            'scope': 'durable_backlog', 'state': 'READY',
            'cartridge': {'id': 'test-tv'}, 'nas_root': str(self.nas),
            'usb_root': str(self.usb),
            'summary': {'scoped_items': 1, 'backup_files': 1,
                        'backup_bytes': len(self.content), 'conflicts': 0, 'ingest_files': 0},
            'actions': [{'direction': 'NAS_TO_USB', 'relative_path': 'Show/1x03.mkv',
                         'size_bytes': len(self.content), 'reason': 'NEW_ON_NAS'}],
            'conflicts': [],
        }

    def test_preview_never_executes(self):
        preview = plan_summary(self.plan)
        self.assertEqual(preview['state'], 'PLAN_ONLY')
        self.assertFalse(preview['backup_authorized'])
        self.assertFalse((self.usb / 'Show').exists())

    def test_digest_changes_for_different_file(self):
        altered = copy.deepcopy(self.plan)
        altered['actions'][0]['relative_path'] = 'Show/1x04.mkv'
        self.assertNotEqual(canonical_plan_digest(self.plan), canonical_plan_digest(altered))

    def test_verified_sandbox_copy_evidence(self):
        result = execute_sandbox_plan(plan=self.plan, sandbox_root=self.root)
        self.assertEqual(result['state'], 'VERIFIED_SANDBOX_PLAN')
        self.assertFalse(result['shared_manifest_updated'])
        self.assertEqual((self.usb / 'Show' / '1x03.mkv').read_bytes(), self.content)
        self.assertEqual(len(result['evidence_preview']['items']), 1)

    def test_collision_cannot_replace(self):
        (self.usb / 'Show').mkdir()
        (self.usb / 'Show' / '1x03.mkv').write_bytes(b'original')
        with self.assertRaises(BackupExecutionError):
            execute_sandbox_plan(plan=self.plan, sandbox_root=self.root)
        self.assertEqual((self.usb / 'Show' / '1x03.mkv').read_bytes(), b'original')

    def test_interruption_no_evidence(self):
        with self.assertRaises(BackupExecutionError):
            execute_sandbox_plan(plan=self.plan, sandbox_root=self.root, fault='interrupt')
        self.assertFalse((self.usb / 'Show' / '1x03.mkv').exists())

    def test_mismatched_summary_fails_closed(self):
        self.plan['summary']['backup_bytes'] = 1
        with self.assertRaises(BackupExecutionError):
            execute_sandbox_plan(plan=self.plan, sandbox_root=self.root)

    def test_multiple_actions_fails_closed(self):
        self.plan['actions'].append(dict(self.plan['actions'][0]))
        with self.assertRaises(BackupExecutionError):
            execute_sandbox_plan(plan=self.plan, sandbox_root=self.root)

    def test_physical_execution_is_disabled(self):
        with self.assertRaisesRegex(BackupExecutionError, 'PHYSICAL_EXECUTION_DISABLED'):
            execute_physical_plan(plan=self.plan)


if __name__ == '__main__':
    unittest.main()
