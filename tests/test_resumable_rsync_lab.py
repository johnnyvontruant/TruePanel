import os
import tempfile
import unittest
import re
from pathlib import Path
from truepanel.cargo.resumable_rsync_lab import LabError, InterruptedTransfer, plan, transfer


class ResumableRsyncLabTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='lm-resume-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / '.loadmaster-lab-only').write_text('LAB_ONLY\n')
        self.nas, self.usb = self.root/'nas', self.root/'usb'
        self.nas.mkdir(); self.usb.mkdir()
        (self.nas/'episode.mkv').write_bytes(os.urandom(1024*512))
        (self.usb/'import.mkv').write_bytes(os.urandom(1024*256))

    def test_nas_to_usb(self):
        intent = plan(self.root, direction='NAS_TO_USB', relative='episode.mkv')
        self.assertEqual(transfer(self.root, intent, transfer_approved=True)['state'], 'NEW_VERIFIED_COPY')
        self.assertEqual((self.usb/'episode.mkv').read_bytes(), (self.nas/'episode.mkv').read_bytes())

    def test_usb_to_nas(self):
        intent = plan(self.root, direction='USB_TO_NAS', relative='import.mkv')
        self.assertEqual(transfer(self.root, intent, transfer_approved=True)['direction'], 'USB_TO_NAS')
        self.assertEqual((self.nas/'import.mkv').read_bytes(), (self.usb/'import.mkv').read_bytes())

    def test_reconcile_without_recopy(self):
        intent = plan(self.root, direction='NAS_TO_USB', relative='episode.mkv')
        transfer(self.root, intent, transfer_approved=True)
        self.assertFalse(transfer(self.root, intent)['new_transfer'])

    def test_no_approval_no_copy(self):
        intent = plan(self.root, direction='NAS_TO_USB', relative='episode.mkv')
        with self.assertRaisesRegex(LabError, 'approval'):
            transfer(self.root, intent)
        self.assertFalse((self.usb/'episode.mkv').exists())

    def test_changed_source(self):
        intent = plan(self.root, direction='NAS_TO_USB', relative='episode.mkv')
        (self.nas/'episode.mkv').write_bytes(b'different')
        with self.assertRaisesRegex(LabError, 'differs'):
            transfer(self.root, intent, transfer_approved=True)

    def test_existing_destination_collision(self):
        intent = plan(self.root, direction='NAS_TO_USB', relative='episode.mkv')
        (self.usb/'episode.mkv').write_bytes(b'keep me')
        with self.assertRaisesRegex(LabError, 'never overwrite'):
            transfer(self.root, intent, transfer_approved=True)
        self.assertEqual((self.usb/'episode.mkv').read_bytes(), b'keep me')

    def test_symlink_refused(self):
        (self.usb/'bad').symlink_to(self.nas, target_is_directory=True)
        with self.assertRaisesRegex(LabError, 'symlink'):
            plan(self.root, direction='USB_TO_NAS', relative='bad/episode.mkv')

    def test_actual_interruption_then_resumption(self):
        source = self.nas/'large-episode.mkv'
        source.write_bytes(os.urandom(12*1024*1024))
        intent = plan(self.root, direction='NAS_TO_USB', relative='large-episode.mkv')
        with self.assertRaises(InterruptedTransfer):
            transfer(self.root, intent, transfer_approved=True,
                     interrupt_after=1.25, bwlimit_kib=512)
        self.assertFalse((self.usb/'large-episode.mkv').exists())
        self.assertTrue(any(p.is_file() and p.stat().st_size > 0
                            for p in (self.usb/'.loadmaster-rsync-stage').rglob('*')))
        # Re-approval is mandatory: the incomplete file is not silently resumed.
        with self.assertRaisesRegex(LabError, 'approval'):
            transfer(self.root, intent)
        result = transfer(self.root, intent, transfer_approved=True)
        self.assertEqual(result['state'], 'NEW_VERIFIED_COPY')
        matched = re.search(r'Matched data: ([\d,]+) bytes', result['rsync_stats'])
        self.assertIsNotNone(matched)
        self.assertGreater(int(matched.group(1).replace(',', '')), 0,
                           'resume must REUSE partial bytes, not copy from zero')
        self.assertEqual((self.usb/'large-episode.mkv').read_bytes(), source.read_bytes())

    def test_actual_interrupted_usb_ingest_resume(self):
        source = self.usb/'new-from-usb.bin'
        source.write_bytes(os.urandom(8*1024*1024))
        intent = plan(self.root, direction='USB_TO_NAS', relative='new-from-usb.bin')
        with self.assertRaises(InterruptedTransfer):
            transfer(self.root, intent, transfer_approved=True,
                     interrupt_after=1.25, bwlimit_kib=512)
        self.assertFalse((self.nas/'new-from-usb.bin').exists())
        with self.assertRaisesRegex(LabError, 'approval'):
            transfer(self.root, intent)
        result = transfer(self.root, intent, transfer_approved=True)
        matched = re.search(r'Matched data: ([\d,]+) bytes', result['rsync_stats'])
        self.assertIsNotNone(matched)
        self.assertGreater(int(matched.group(1).replace(',', '')), 0)
        self.assertEqual((self.nas/'new-from-usb.bin').read_bytes(), source.read_bytes())

    def test_atomic_publish_refuses_late_collision(self):
        from unittest.mock import patch
        from truepanel.cargo import resumable_rsync_lab as code
        intent = plan(self.root, direction='NAS_TO_USB', relative='episode.mkv')
        actual = code._noreplace_rename
        def race(source, target):
            target.write_bytes(b'other writer got here first')
            return actual(source, target)
        with patch.object(code, '_noreplace_rename', side_effect=race):
            with self.assertRaisesRegex(LabError, 'collision'):
                transfer(self.root, intent, transfer_approved=True)
        self.assertEqual((self.usb/'episode.mkv').read_bytes(), b'other writer got here first')

    def test_refuse_non_disposable_root(self):
        with self.assertRaises(LabError):
            plan(Path('/mnt'), direction='NAS_TO_USB', relative='test.mkv')


if __name__ == '__main__':
    unittest.main()
