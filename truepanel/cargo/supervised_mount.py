"""Host-controlled, bounded exFAT write window for one supervised copy.

Stage-only candidate. Does not act until explicitly entered by privileged host.
Never mounts another device, overwrites files or leaves writes unverified.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

from .backup_executor import BackupExecutionError, attest_cartridge_read_only


class SupervisedWriteWindow:
    """Temporarily remount the SAME authenticated cartridge writable.

    A trusted Host Agent must supply this context only after physical
    confirmation. Always attempts to restore read-only on exit.
    """
    def __init__(self, *, mount: Path, uuid: str, by_id: str,
                 runner=None):
        self.mount = mount
        self.uuid = uuid
        self.by_id = by_id
        self._runner = runner or self._run
        self._entered = False

    @staticmethod
    def _run(cmd):
        return subprocess.run(cmd, check=True, capture_output=True,
                              text=True, timeout=30)

    def _mount(self, mode: str):
        if mode not in ('ro', 'rw'):
            raise BackupExecutionError('invalid mount transition')
        self._runner(['mount', '-o', 'remount,' + mode, str(self.mount)])

    def __enter__(self):
        if self._entered:
            raise BackupExecutionError('write window already entered')
        # The hardware is first confirmed while read-only. No mount or
        # path substitution may be accepted on an arbitrary root.
        attest_cartridge_read_only(
            mount=self.mount, registered_uuid=self.uuid,
            registered_by_id=self.by_id)
        self._entered = True
        try:
            self._mount('rw')
        except BaseException:
            try:
                self._mount('ro')
                attest_cartridge_read_only(
                    mount=self.mount, registered_uuid=self.uuid,
                    registered_by_id=self.by_id)
            except BaseException as restore_error:
                raise BackupExecutionError(
                    'CRITICAL: failed to restore cartridge read-only') from restore_error
            self._entered = False
            raise
        return self

    def __exit__(self, typ, value, tb):
        try:
            self._mount('ro')
            attest_cartridge_read_only(
                mount=self.mount, registered_uuid=self.uuid,
                registered_by_id=self.by_id)
        except BaseException as error:
            raise BackupExecutionError(
                'CRITICAL: cartridge read-only restoration not verified') from error
        finally:
            self._entered = False
        return False
