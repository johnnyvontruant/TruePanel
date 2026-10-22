"""Bounded read-only batch preview tests."""
import unittest
from pathlib import Path
from unittest.mock import patch
from truepanel.cargo.backup_executor import BackupExecutionError
from tools.loadmaster_batch_preview import preview


class BatchPreviewTests(unittest.TestCase):
    def call(self, sources):
        return preview(
            registry=Path('/registry'), backlog=Path('/backlog'),
            cartridge_id='tv-n-z', mount=Path('/mount'),
            by_id='/dev/disk/by-id/verified', sources=sources)

    def test_rejects_empty_and_more_than_three(self):
        for sources in ([], [Path('/x')]*4):
            with self.assertRaises(BackupExecutionError):
                self.call(sources)

    def test_rejects_duplicate_and_relative(self):
        for sources in ([Path('/x'), Path('/x')], [Path('relative')]):
            with self.assertRaises(BackupExecutionError):
                self.call(sources)

    def test_preview_never_grants_write(self):
        def inspect(**kwargs):
            source = kwargs['source_path']
            return {'state':'READ_ONLY_TRANSACTION_ACCEPTED',
                    'source':str(source), 'destination': '/usb'+str(source),
                    'size_bytes': 10, 'available_bytes': 100,
                    'source_sha256':'a'*64, 'plan_digest':'b'*64}
        with patch('tools.loadmaster_batch_preview.inspect_transaction', side_effect=inspect) as mock:
            result = self.call([Path('/a'), Path('/b'), Path('/c')])
        self.assertEqual(mock.call_count, 3)
        self.assertEqual(result['state'], 'BATCH_PREVIEW_ONLY')
        self.assertEqual(result['total_bytes'], 30)
        self.assertFalse(result['backup_authorized'])
        self.assertFalse(result['executed'])

    def test_insufficient_space_fails_closed(self):
        def inspect(**kwargs):
            return {'state':'READ_ONLY_TRANSACTION_ACCEPTED',
                    'source':str(kwargs['source_path']),
                    'destination':'/usb'+str(kwargs['source_path']),
                    'size_bytes': 15,'available_bytes': 20,
                    'source_sha256':'a'*64, 'plan_digest':'b'*64}
        with patch('tools.loadmaster_batch_preview.inspect_transaction', side_effect=inspect):
            with self.assertRaisesRegex(BackupExecutionError, 'capacity'):
                self.call([Path('/a'), Path('/b')])


if __name__ == '__main__':
    unittest.main()
