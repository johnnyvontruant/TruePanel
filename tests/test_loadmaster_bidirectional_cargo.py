"""Bidirectional discovery and rsync sandbox acceptance."""
import hashlib
import tempfile
import unittest
from pathlib import Path
from truepanel.cargo.backup_executor import BackupExecutionError
from truepanel.cargo.bidirectional_discovery import discover_bidirectional
from truepanel.cargo.resumable_rsync import rsync_sandbox_copy

class TestBidirectionalCargo(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.sandbox=Path(self.temp.name)
        self.nas=self.sandbox/'nas'
        self.usb=self.sandbox/'usb'
        self.nas.mkdir()
        self.usb.mkdir()

    def put(self, root, path, data):
        dest=root/path
        dest.parent.mkdir(exist_ok=True)
        dest.write_bytes(data)
        return dest

    def test_bidirectional_classification_and_conflicts(self):
        self.put(self.nas,'Show/only-nas.mkv',b'A')
        self.put(self.usb,'Show/only-usb.mkv',b'B')
        self.put(self.nas,'Show/same.mkv',b'C')
        self.put(self.usb,'Show/same.mkv',b'C')
        self.put(self.nas,'Show/conflict.mkv',b'D')
        self.put(self.usb,'Show/conflict.mkv',b'E')
        result=discover_bidirectional(nas_root=self.nas,usb_root=self.usb)
        self.assertEqual(result['counts'], {
            'export_to_usb':1,'ingest_to_nas':1,'verified_match':1,'conflict':1})
        self.assertFalse(result['authorized'])
        self.assertFalse(result['deleted'])

    def test_sandbox_export_and_ingest_no_overwrite(self):
        a=self.put(self.nas,'Show/export.mkv',b'abc'*100000)
        b=self.put(self.usb,'Show/ingest.mkv',b'xyz'*100000)
        for src,dst,name,file in ((self.nas,self.usb,'Show/export.mkv',a),
                                  (self.usb,self.nas,'Show/ingest.mkv',b)):
            data=file.read_bytes()
            result=rsync_sandbox_copy(sandbox=self.sandbox,
                      source_root=src,destination_root=dst,relative_path=name,
                      expected_size=len(data),
                      expected_sha256=hashlib.sha256(data).hexdigest())
            self.assertEqual(result['state'],'RSYNC_SANDBOX_VERIFIED')
            self.assertEqual((dst/name).read_bytes(),data)
            with self.assertRaisesRegex(BackupExecutionError,'occupied'):
                rsync_sandbox_copy(sandbox=self.sandbox,source_root=src,
                    destination_root=dst,relative_path=name,
                    expected_size=len(data),
                    expected_sha256=hashlib.sha256(data).hexdigest())

    def test_reject_wrong_digest_and_preserve_target(self):
        self.put(self.nas,'Show/new.mkv',b'real')
        with self.assertRaisesRegex(BackupExecutionError,'disagrees'):
            rsync_sandbox_copy(sandbox=self.sandbox,source_root=self.nas,
                destination_root=self.usb,relative_path='Show/new.mkv',
                expected_size=4,expected_sha256='0'*64)
        self.assertFalse((self.usb/'Show/new.mkv').exists())

    def test_reject_symlinked_inventory(self):
        (self.nas/'Show').symlink_to(self.usb, target_is_directory=True)
        with self.assertRaisesRegex(BackupExecutionError,'symlink'):
            discover_bidirectional(nas_root=self.nas,usb_root=self.usb)

if __name__ == '__main__':
    unittest.main()
