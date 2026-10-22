"""End-to-end sandbox integration: callback -> approval -> pinned copy -> manifest."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from truepanel.cargo.batch_authorization import BatchApprovalScope, BatchItem
from truepanel.cargo.batch_host_simulation import BatchSessionSpec
from truepanel.cargo.batch_durable_simulation import DurableSimulatedBatchHostSession
from truepanel.cargo.batch_host_integration_lab import run_simulated_host_batch
from truepanel.cargo.copy_button import CopyButtonConfirmation, LoadmasterCopyButtonGate
from truepanel.host.loadmaster_copy_button import LoadmasterCopyButtonService
from truepanel.host.loadmaster_session_bridge import LoadmasterHostSessionBridge
from truepanel.cargo.backup_executor import BackupExecutionError


class Reader:
    def read_level(self):
        return 1


class HostBatchIntegrationTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.nas = self.root/'nas'
        self.usb = self.root/'usb'
        self.nas.mkdir(); self.usb.mkdir()
        self.journal = self.root/'journal'
        self.journal.mkdir(mode=0o700)
        self.manifest = self.root/'manifest.json'
        self.t = 100.0
        items = []
        for i in range(3):
            rel = f'Show {i}/ep.mkv'
            path = self.nas/rel
            path.parent.mkdir()
            data = bytes([i+1])*(8192+i)
            path.write_bytes(data)
            items.append(BatchItem(rel, len(data), hashlib.sha256(data).hexdigest()))
        self.items = tuple(items)
        self.scope = BatchApprovalScope(cartridge_id='tv-n-z', cartridge_uuid='6988-53EB', items=self.items)
        service = LoadmasterCopyButtonService(reader=Reader(),
            gate=LoadmasterCopyButtonGate(read_level=lambda: 1, clock=lambda: self.t))
        session = DurableSimulatedBatchHostSession(clock=lambda: self.t,
            fresh_digest=lambda: self.scope.digest, journal_root=self.journal)
        self.bridge = LoadmasterHostSessionBridge(service=service, session=session)
        self.service = service
        self.spec = BatchSessionSpec('tv-n-z','6988-53EB','2532EA8D3DC7',self.items)

    def approve(self):
        self.bridge.prepare_and_arm(self.spec)
        self.t = 101.
        self.service.on_confirmation(CopyButtonConfirmation(
            cartridge_id='tv-n-z',cartridge_uuid='6988-53EB',
            device_serial='2532EA8D3DC7',plan_digest=self.scope.digest,
            confirmed_at_monotonic=self.t))

    def execute(self, reattest=None):
        return run_simulated_host_batch(sandbox=self.root,nas=self.nas,usb=self.usb,
            manifest=self.manifest,scope=self.scope,bridge=self.bridge,
            reattest=reattest or (lambda: self.items))

    def test_complete_three_file_end_to_end(self):
        self.approve()
        result = self.execute()
        self.assertEqual(result['state'], 'HOST_BATCH_VERIFIED')
        self.assertEqual(len(result['completed']),3)
        for item in self.items:
            self.assertEqual((self.nas/item.relative_path).read_bytes(),
                             (self.usb/item.relative_path).read_bytes())
        self.assertEqual(len(json.loads(self.manifest.read_text())['items']),3)
        self.assertEqual(len(list(self.journal.glob('*.consumed'))),1)

    def test_changed_plan_never_consumes(self):
        self.approve()
        with self.assertRaisesRegex(BackupExecutionError,'changed'):
            self.execute(lambda: ())
        self.assertFalse(list(self.journal.glob('*.consumed')))
        self.assertFalse(self.manifest.exists())

    def test_destination_collision_is_never_overwritten(self):
        occupied = self.usb/self.items[0].relative_path
        occupied.parent.mkdir()
        occupied.write_bytes(b'untouchable')
        self.approve()
        with self.assertRaisesRegex(BackupExecutionError,'occupied'):
            self.execute()
        self.assertEqual(occupied.read_bytes(),b'untouchable')
        self.assertEqual(len(list(self.journal.glob('*.consumed'))),1)
        self.assertFalse(self.manifest.exists())

    def test_scope_cannot_be_replayed(self):
        self.approve()
        self.execute()
        with self.assertRaises(BackupExecutionError):
            self.execute()


if __name__ == '__main__':
    unittest.main()
