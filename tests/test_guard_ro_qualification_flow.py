"""Strictly mock-only control flow for the RO-only host-namespace qualification."""
from __future__ import annotations

import json
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from tools import loadmaster_ro_rw_qualification as q


class FakeOwner:
    pid = 38232

    def __init__(self, on_kill):
        self.killed = False
        self.on_kill = on_kill

    def poll(self):
        return -9 if self.killed else None

    def kill(self):
        self.killed = True
        self.on_kill()

    def wait(self, timeout=5):
        return -9


class RoOnlyQualificationTest(unittest.TestCase):
    def test_kill_synthetic_owner_without_remount_rw_or_timer(self):
        with tempfile.TemporaryDirectory() as td:
            original = q.STATE
            q.STATE = Path(td)
            self.addCleanup(setattr, q, 'STATE', original)
            nonce = 'f' * 32
            status = Path(td) / (nonce + '.json')
            owner = FakeOwner(lambda: status.write_text(json.dumps({'state':'RESTORED_RO'})))
            mount_calls = []
            def fake_mount(pin): return 'ro'
            def fake_call(argv, *, timeout=12):
                if argv[0] == 'systemd-run':
                    self.assertFalse(any('ProtectSystem=full' in x for x in argv))
                    self.assertIn('--property=PrivateMounts=no',argv)
                mount_calls.append(argv)
                return 'Running as unit'
            with patch.object(q, 'get_modules', return_value=(lambda: types.SimpleNamespace(mount=Path('/test'), uuid='6ADA-80D5'),fake_mount,lambda p:123,lambda **k: True)), \
                 patch.object(q, 'verify_baseline'), \
                 patch.object(q, 'call',side_effect=fake_call), \
                 patch.object(q, 'unit_fields',return_value={'ActiveState':'inactive','Result':'success','ExecMainStatus':'0'}), \
                 patch.object(q.subprocess,'Popen',return_value=owner), \
                 patch.object(q.subprocess,'run') as run, \
                 patch.object(q.secrets,'token_hex',return_value=nonce):
                self.assertEqual(q.live_rw_test(read_only_qualification=True),0)
            self.assertTrue(owner.killed)
            run.assert_not_called()
            self.assertEqual(sum(argv[0]=='systemd-run' for argv in mount_calls),1)

    def test_unready_guard_blocks_ro_qualification_without_remount(self):
        # Static contract: executable mode --qualify-guard-ro is still bounded
        # by the same live systemd READY gate as --live-rw.
        src = (Path(q.__file__)).read_text()
        self.assertIn("if read_only_qualification:",src)
        self.assertLess(src.index("raise RuntimeError('HOLD: watchdog not independently READY')"),
                        src.index("if read_only_qualification:"))


if __name__ == '__main__':
    unittest.main()
