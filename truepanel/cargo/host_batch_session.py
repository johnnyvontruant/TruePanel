"""Host-owned batch session with durable, single-use physical confirmation.

Stage only. The host must supply an independently verified read-only batch
snapshot; the callback is exclusively owned by LoadmasterHostSessionBridge.
No GPIO polling, remount, or physical execution occurs in this module.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .backup_executor import BackupExecutionError, DurableConfirmationJournal, DurableHostAuthorizationSession
from .batch_authorization import BatchItem, batch_digest
from .copy_button import LoadmasterPhysicalPreflight


@dataclass(frozen=True)
class HostBatchSpec:
    cartridge_id: str
    cartridge_uuid: str
    device_serial: str
    items: tuple[BatchItem, ...]
    journal_root: Path


class HostBatchApprovalSession:
    """Host callback proof, fresh-intent check, durable burn; no copy rights."""

    def __init__(self, *, reattest: Callable[[], tuple[BatchItem, ...]],
                 clock=time.monotonic):
        self._reattest = reattest
        self._clock = clock
        self._state = 'NEW'
        self._spec = None
        self._digest = None
        self._authorization = None

    def prepare(self, spec: HostBatchSpec) -> LoadmasterPhysicalPreflight:
        if self._state != 'NEW':
            raise BackupExecutionError('batch host session already prepared')
        if (type(spec) is not HostBatchSpec or not spec.device_serial
                or not spec.journal_root.is_absolute()):
            raise BackupExecutionError('invalid host batch spec')
        digest = batch_digest(cartridge_id=spec.cartridge_id,
                              cartridge_uuid=spec.cartridge_uuid, items=spec.items)
        if self._reattest() != spec.items:
            raise BackupExecutionError('batch inspection changed before arming')
        journal = DurableConfirmationJournal(spec.journal_root)
        auth = DurableHostAuthorizationSession(clock=self._clock, journal=journal)
        auth.arm(cartridge_id=spec.cartridge_id,
                 cartridge_uuid=spec.cartridge_uuid,
                 device_serial=spec.device_serial, plan_digest=digest)
        self._authorization = auth
        self._spec = spec
        self._digest = digest
        self._state = 'PREPARED'
        return LoadmasterPhysicalPreflight(
            cartridge_id=spec.cartridge_id, cartridge_uuid=spec.cartridge_uuid,
            device_serial=spec.device_serial, plan_state='READY',
            backup_files=len(spec.items),
            backup_bytes=sum(i.size_bytes for i in spec.items),
            baseline_verified=True, identity_verified=True,
            backlog_verified=True, plan_digest=digest,
            generated_at_monotonic=self._clock())

    def on_confirmation(self, confirmation) -> None:
        if self._state != 'PREPARED':
            raise BackupExecutionError('batch host session not armed')
        self._authorization.on_confirmation(confirmation)

    def consume_after_physical_press(self) -> dict:
        if self._state != 'PREPARED':
            raise BackupExecutionError('batch confirmation unavailable')
        self._state = 'SPENT'
        try:
            fresh = self._reattest()
            if fresh != self._spec.items:
                raise BackupExecutionError('batch changed since approval')
            result = self._authorization.consume()
            if result['plan_digest'] != self._digest:
                raise BackupExecutionError('durable approval digest mismatch')
            return {**result, 'state': 'HOST_APPROVAL_EVIDENCE_ONLY',
                    'physical_execution_enabled': False,
                    'backup_authorized': False, 'executed': False}
        finally:
            self._authorization.disarm()

    def disarm(self) -> None:
        self._state = 'SPENT'
        if self._authorization is not None:
            self._authorization.disarm()

    def execute_physical(self, *args, **kwargs):
        raise BackupExecutionError('PHYSICAL_EXECUTION_DISABLED')
