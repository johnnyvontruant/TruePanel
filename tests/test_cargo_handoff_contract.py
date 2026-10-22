"""Non-actuating physical handoff validation."""
import copy
import unittest
from truepanel.cargo.backup_coordinator import validate_physical_handoff, canonical_plan_digest
from truepanel.cargo.backup_executor import BackupExecutionError

class HandoffTests(unittest.TestCase):
    def setUp(self):
        self.plan = dict(schema_version=1, read_only=True, state="READY",
            scope="durable_backlog", delete_policy="never", conflicts=[],
            cartridge={"id":"tv-n-z"},
            summary=dict(scoped_items=1, backup_files=1, backup_bytes=5, conflicts=0, ingest_files=0),
            actions=[dict(direction="NAS_TO_USB", relative_path="Show/1x03.mkv", size_bytes=5)])
        digest = canonical_plan_digest(self.plan)
        self.approval = dict(state="HOST_APPROVAL_EVIDENCE_ONLY", cartridge_id="tv-n-z",
            plan_digest=digest, executed=False, backup_authorized=False,
            physical_execution_enabled=False)
        self.readiness = dict(state="READ_ONLY_PREPARED", cartridge_id="tv-n-z",
            uuid="6988-53EB", mount_read_only=True, device_serial_registered=True,
            plan_digest=digest, relative_path="Show/1x03.mkv", size_bytes=5)

    def check(self):
        return validate_physical_handoff(plan=self.plan,
            approval=self.approval, readiness=self.readiness)

    def test_matching_consumed_handoff(self):
        self.assertEqual(self.check()["state"], "PHYSICAL_HANDOFF_CONTRACT_VALIDATED")
        self.assertFalse(self.check()["executed"])

    def test_rejects_unconsumed_handoff(self):
        self.approval["state"] = "HOST_ARMED_EVIDENCE_ONLY"
        with self.assertRaises(BackupExecutionError): self.check()

    def test_rejects_wrong_cartridge(self):
        self.approval["cartridge_id"] = "other"
        with self.assertRaises(BackupExecutionError): self.check()

    def test_rejects_changed_plan(self):
        self.plan["actions"][0]["relative_path"] = "Show/1x04.mkv"
        with self.assertRaises(BackupExecutionError): self.check()

    def test_rejects_unverified_serial(self):
        self.readiness["device_serial_registered"] = False
        with self.assertRaises(BackupExecutionError): self.check()

if __name__ == "__main__":
    unittest.main()
