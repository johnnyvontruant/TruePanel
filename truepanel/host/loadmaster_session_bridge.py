"""Non-actuating host-owned Copy-button session bridge.

Connects the GPIO service callback to the durable approval session.  A
confirmation is evidence only; this module has no physical copy operation.
"""
from __future__ import annotations

import threading
from typing import Any

from truepanel.cargo.backup_executor import BackupExecutionError
from truepanel.cargo.physical_session import ReadOnlyHostSession, PhysicalSessionSpec
from truepanel.host.loadmaster_copy_button import LoadmasterCopyButtonService


class LoadmasterHostSessionBridge:
    """Owns one approval session and one host Copy-button service.

    The service's on_confirmation must point to this bridge before arming.
    Do not expose the service or callback as an external authorization API.
    """

    def __init__(self, *, service: LoadmasterCopyButtonService,
                 session: ReadOnlyHostSession):
        if service.started:
            raise BackupExecutionError('button service already running')
        if service.on_confirmation is not None:
            raise BackupExecutionError('button callback already assigned')
        self._lock = threading.RLock()
        self._service = service
        self._session = session
        self._state = 'NEW'
        service.on_confirmation = self._on_confirmation

    def prepare_and_arm(self, spec: PhysicalSessionSpec) -> dict[str, Any]:
        with self._lock:
            if self._state != 'NEW':
                raise BackupExecutionError('bridge cannot be rearmed')
            preflight = self._session.prepare(spec)
            try:
                self._service.arm(preflight)
            except BaseException:
                self._session.disarm()
                self._state = 'CLOSED'
                raise
            self._state = 'ARMED'
            return {'state': 'HOST_ARMED_EVIDENCE_ONLY',
                    'plan_digest': preflight.plan_digest,
                    'backup_files': preflight.backup_files,
                    'executed': False}

    def _on_confirmation(self, confirmation) -> None:
        with self._lock:
            if self._state != 'ARMED':
                raise BackupExecutionError('bridge is not armed')
            self._session.on_confirmation(confirmation)
            self._state = 'CONFIRMED'

    def consume_read_only(self) -> dict[str, Any]:
        with self._lock:
            if self._state != 'CONFIRMED':
                raise BackupExecutionError('physical confirmation not received')
            self._state = 'CLOSED'
            try:
                evidence = self._session.consume_after_physical_press()
                return {**evidence, 'executed': False,
                        'physical_execution_enabled': False}
            finally:
                self._service.disarm(reason='approval_consumed')
                self._session.disarm()

    def disarm(self) -> None:
        with self._lock:
            self._state = 'CLOSED'
            self._service.disarm(reason='bridge_closed')
            self._session.disarm()

    def execute_physical(self, *args, **kwargs):
        raise BackupExecutionError('PHYSICAL_EXECUTION_DISABLED')
