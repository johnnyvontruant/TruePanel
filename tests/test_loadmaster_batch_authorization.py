"""Fail-closed unit tests for batch-scoped confirmation. No physical IO."""
import unittest
from dataclasses import replace

from truepanel.cargo.backup_executor import BackupExecutionError
from truepanel.cargo.batch_authorization import BatchItem, BatchApprovalScope, batch_digest


class BatchScopeTests(unittest.TestCase):
    def setUp(self):
        self.items = tuple(BatchItem(f'Show {i}/ep.mkv', 100 + i, f'{i+1:064x}')
                           for i in range(3))
        self.scope = BatchApprovalScope(
            cartridge_id='tv-n-z', cartridge_uuid='6988-53EB', items=self.items)

    def receipt(self):
        return {'state': 'HOST_APPROVAL_EVIDENCE_ONLY',
                'cartridge_id': 'tv-n-z', 'plan_digest': self.scope.digest,
                'physical_execution_enabled': False, 'executed': False}

    def test_valid_full_batch_once(self):
        self.assertEqual(self.scope.consume(host_evidence=self.receipt(),
                                            fresh_digest=self.scope.digest), self.items)
        with self.assertRaisesRegex(BackupExecutionError, 'spent'):
            self.scope.consume(host_evidence=self.receipt(), fresh_digest=self.scope.digest)

    def test_modified_order_changes_digest(self):
        other = batch_digest(cartridge_id='tv-n-z', cartridge_uuid='6988-53EB',
                             items=tuple(reversed(self.items)))
        self.assertNotEqual(self.scope.digest, other)
        with self.assertRaisesRegex(BackupExecutionError, 'mismatch'):
            self.scope.consume(host_evidence=self.receipt(), fresh_digest=other)

    def test_changed_hash_and_size_change_digest(self):
        for changed in (replace(self.items[0], sha256='a'*64),
                        replace(self.items[0], size_bytes=999)):
            other = batch_digest(cartridge_id='tv-n-z', cartridge_uuid='6988-53EB',
                                 items=(changed, *self.items[1:]))
            self.assertNotEqual(other, self.scope.digest)

    def test_wrong_cartridge_refused(self):
        evidence = self.receipt()
        evidence['cartridge_id'] = 'other'
        with self.assertRaisesRegex(BackupExecutionError, 'mismatch'):
            self.scope.consume(host_evidence=evidence, fresh_digest=self.scope.digest)

    def test_preview_not_authority(self):
        evidence = self.receipt()
        evidence['state'] = 'BATCH_PREVIEW_ONLY'
        with self.assertRaisesRegex(BackupExecutionError, 'mismatch'):
            self.scope.consume(host_evidence=evidence, fresh_digest=self.scope.digest)

    def test_rejects_four_files_or_duplicates(self):
        with self.assertRaises(BackupExecutionError):
            batch_digest(cartridge_id='tv-n-z', cartridge_uuid='6988-53EB',
                         items=self.items + (self.items[0],))
        with self.assertRaises(BackupExecutionError):
            batch_digest(cartridge_id='tv-n-z', cartridge_uuid='6988-53EB',
                         items=(self.items[0], self.items[0]))

    def test_unsafe_paths_refused(self):
        for bad in ('../escape', 'Show/../ep', '/etc/shadow', 'Show//ep', 'Show/./ep'):
            with self.subTest(path=bad):
                with self.assertRaises(BackupExecutionError):
                    batch_digest(cartridge_id='tv-n-z', cartridge_uuid='6988-53EB',
                                 items=(replace(self.items[0], relative_path=bad),))


if __name__ == '__main__':
    unittest.main()
