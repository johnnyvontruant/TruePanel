"""Static safety checks: launch properties must preserve host mount changes."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class HostNamespaceContract(unittest.TestCase):
    def test_rw_qualification_no_mount_isolation(self):
        src = (ROOT / 'tools/loadmaster_ro_rw_qualification.py').read_text()
        self.assertNotIn('ProtectSystem=full', src)
        self.assertIn("'--property=PrivateMounts=no'", src)
        self.assertIn('same_host_mount_namespace', src)

    def test_ro_qualification_no_mount_isolation(self):
        src = (ROOT / 'tools/loadmaster_ro_guard_qualification.py').read_text()
        self.assertNotIn('ProtectSystem=full', src)
        self.assertIn("'--property=PrivateMounts=no'", src)

    def test_guard_preflight_requires_real_host_namespace(self):
        src = (ROOT / 'tools/loadmaster_spare_ro_guard.py').read_text()
        self.assertIn('same_host_mount_namespace(os.getpid())', src)

    def test_host_verifier_checks_actual_service_namespace(self):
        src = (ROOT / 'truepanel/cargo/independent_ro_watchdog.py').read_text()
        self.assertIn("same_host_mount_namespace(data['guardian_pid'])", src)


if __name__ == '__main__':
    unittest.main()
