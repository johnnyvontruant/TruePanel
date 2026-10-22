import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from truepanel.cargo.backup_evidence_commit import commit_verified_backup
from truepanel.cargo.backup_executor import BackupExecutionError

class EvidenceCommitTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.source = root / 'source.mkv'
        self.dest = root / 'copy.mkv'
        self.manifest = root / 'manifest.json'
        self.source.write_bytes(b'episode' * 100)
        self.dest.write_bytes(self.source.read_bytes())
        self.digest = hashlib.sha256(self.source.read_bytes()).hexdigest()

    def run_commit(self):
        return commit_verified_backup(source=self.source, destination=self.dest,
            manifest=self.manifest, expected_size=self.source.stat().st_size,
            expected_sha256=self.digest)

    def test_commit_verified(self):
        self.assertEqual(self.run_commit()['state'], 'EVIDENCE_RECORDED')
        self.assertEqual(json.loads(self.manifest.read_text())['items'][0]['sha256'], self.digest)

    def test_crash_recovery_retry_idempotent(self):
        self.run_commit()
        raw = self.manifest.read_bytes()
        self.assertEqual(self.run_commit()['state'], 'ALREADY_RECORDED')
        self.assertEqual(raw, self.manifest.read_bytes())

    def test_preexisting_manifest_retained(self):
        payload = {'kind': 'truepanel.cargo_backup_manifest', 'schema_version': 1,
                   'created_at': '2026-10-21T00:00:00+00:00', 'source': 'existing',
                   'items': [{'path': '/some/older/movie.mkv', 'size_bytes': 2,
                              'backed_up_at': '2026-10-20T00:00:00+00:00'}]}
        self.manifest.write_text(json.dumps(payload))
        self.run_commit()
        self.assertEqual(len(json.loads(self.manifest.read_text())['items']), 2)

    def test_live_legacy_manifest_without_created_at_preserved(self):
        # Shape of the existing TruePanel physical producer manifest.
        payload = {'kind': 'truepanel.cargo_backup_manifest', 'schema_version': 1,
                   'source': 'truepanel-loadmaster-physical',
                   'items': [{'path': '/mnt/HDDs/Movies/Movies 1-D/Collateral (2004)/Collateral (2004).mkv',
                              'size_bytes': 18897361329,
                              'backed_up_at': '2026-10-04T04:43:26.216109+00:00'}]}
        self.manifest.write_text(json.dumps(payload))
        self.assertEqual(self.run_commit()['state'], 'EVIDENCE_RECORDED')
        merged = json.loads(self.manifest.read_text())
        self.assertEqual(merged['items'][0], payload['items'][0])
        self.assertEqual(merged['items'][1]['sha256'], self.digest)
        self.assertEqual(merged['source'], 'truepanel-loadmaster-physical')
        self.assertIn('created_at', merged)

    def test_invalid_legacy_manifest_not_silently_replaced(self):
        payload = {'kind': 'truepanel.cargo_backup_manifest', 'schema_version': 1,
                   'source': 'truepanel-loadmaster-physical',
                   'items': [{'path': '/old/movie.mkv', 'size_bytes': -1,
                              'backed_up_at': '2026-10-04T04:43:26+00:00'}]}
        raw = json.dumps(payload)
        self.manifest.write_text(raw)
        with self.assertRaises(BackupExecutionError): self.run_commit()
        self.assertEqual(self.manifest.read_text(), raw)

    def test_missing_copy_does_not_report(self):
        self.dest.unlink()
        with self.assertRaises(OSError):
            self.run_commit()
        self.assertFalse(self.manifest.exists())

    def test_corrupt_copy_does_not_report(self):
        self.dest.write_bytes(b'corrupt')
        with self.assertRaisesRegex(BackupExecutionError, 'mismatch'):
            self.run_commit()
        self.assertFalse(self.manifest.exists())

    def test_conflicting_existing_entry_preserved(self):
        payload = {'kind': 'truepanel.cargo_backup_manifest', 'schema_version': 1,
                   'created_at': '2026-10-21T00:00:00+00:00', 'source': 'existing',
                   'items': [{'path': str(self.source), 'size_bytes': 999,
                              'backed_up_at': '2026-10-20T00:00:00+00:00'}]}
        self.manifest.write_text(json.dumps(payload))
        with self.assertRaisesRegex(BackupExecutionError, 'conflicting'):
            self.run_commit()
        self.assertEqual(json.loads(self.manifest.read_text()), payload)

    def test_symlink_destination_refused(self):
        self.dest.unlink()
        self.dest.symlink_to(self.source)
        with self.assertRaisesRegex(BackupExecutionError, 'symlink'):
            self.run_commit()

    def test_invalid_existing_manifest_refused(self):
        self.manifest.write_text('not json')
        with self.assertRaisesRegex(BackupExecutionError, 'unreadable'):
            self.run_commit()
        self.assertEqual(self.manifest.read_text(), 'not json')

if __name__ == '__main__':
    unittest.main()
