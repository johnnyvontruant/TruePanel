import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace
from truepanel.cargo.backup_executor import BackupExecutionError
from truepanel.cargo.physical_transaction_dry_run import inspect_transaction

class TransactionDryRunTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.mount = self.root / 'mount'
        (self.mount / 'TV N-Z' / 'Show').mkdir(parents=True)
        self.source = self.root / 'episode.mkv'
        self.source.write_bytes(b'example episode')
        self.args = dict(registry=self.root/'registry.json', backlog=self.root/'backlog.json',
            cartridge_id='tv-n-z', mount=self.mount, by_id='fake', source_path=self.source)
        self.response = dict(cartridge_id='tv-n-z', relative_path='Show/episode.mkv',
            size_bytes=len(self.source.read_bytes()), plan_digest='abc',
            device_serial_registered=True, executed=False, backup_authorized=False)
        p = patch('truepanel.cargo.physical_transaction_dry_run.probe_one_episode', return_value=self.response)
        c = patch('truepanel.cargo.cartridges.load_cartridge_registry', return_value=[SimpleNamespace(cartridge_id='tv-n-z', usb_relative_path='TV N-Z')])
        self.probe = p.start(); c.start(); self.addCleanup(p.stop); self.addCleanup(c.stop)
    def check(self):
        return inspect_transaction(**self.args)
    def test_success_no_write(self):
        result = self.check()
        self.assertEqual(result['state'], 'READ_ONLY_TRANSACTION_ACCEPTED')
        self.assertFalse(result['executed'])
        self.assertFalse((self.mount / 'TV N-Z' / 'Show' / 'episode.mkv').exists())
        self.assertEqual(len(result['source_sha256']),64)
    def test_unregistered_serial(self):
        self.response['device_serial_registered'] = False
        with self.assertRaises(BackupExecutionError): self.check()
    def test_existing_destination(self):
        (self.mount / 'TV N-Z' / 'Show' / 'episode.mkv').write_bytes(b'exists')
        with self.assertRaises(BackupExecutionError): self.check()
    def test_destination_symlink(self):
        (self.mount / 'TV N-Z' / 'Show' / 'episode.mkv').symlink_to(self.source)
        with self.assertRaises(BackupExecutionError): self.check()
    def test_source_symlink(self):
        another = self.root/'real'; self.source.rename(another); self.source.symlink_to(another)
        with self.assertRaises(BackupExecutionError): self.check()
    def test_bad_size(self):
        self.response['size_bytes'] += 1
        with self.assertRaises(BackupExecutionError): self.check()
    def test_unsafe_relative(self):
        self.response['relative_path'] = '../escape.mkv'
        with self.assertRaises(BackupExecutionError): self.check()
    def test_changed_plan(self):
        changed = dict(self.response, plan_digest='changed')
        self.probe.side_effect = [self.response,changed]
        with self.assertRaisesRegex(BackupExecutionError, 'plan changed'): self.check()
    def test_missing_library_root(self):
        (self.mount / 'TV N-Z' / 'Show').rmdir()
        (self.mount / 'TV N-Z').rmdir()
        with self.assertRaises(BackupExecutionError): self.check()

if __name__ == '__main__': unittest.main()
