"""Read-only host session coordinating a one-file Loadmaster approval.

No filesystem actuator exists in this module. The GPIO confirmation is
obtained only from a host-owned service callback. For development validation,
the caller may supply a simulated reader; that cannot grant USB write access.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .backup_executor import (
    BackupExecutionError, DurableConfirmationJournal,
    DurableHostAuthorizationSession,
)
from .copy_button import LoadmasterPhysicalPreflight
from .physical_readiness import probe_one_episode


@dataclass(frozen=True)
class PhysicalSessionSpec:
    registry: Path
    backlog: Path
    cartridge_id: str
    mount: Path
    by_id: str
    source_path: Path
    journal_root: Path


class ReadOnlyHostSession:
    """Read-only preparation and one-shot authorization handoff.

    Caller-owned service must use this session's on_confirmation callback.
    A caller cannot request a physical transfer through this class.
    """

    def __init__(self, *, clock=time.monotonic):
        self._clock = clock
        self._authorization = None
        self._preflight = None
        self._spec = None
        self._state = 'NEW'

    def prepare(self, spec: PhysicalSessionSpec) -> LoadmasterPhysicalPreflight:
        if self._state != 'NEW':
            raise BackupExecutionError('session already prepared')
        readiness = probe_one_episode(
            registry=spec.registry, backlog=spec.backlog,
            cartridge_id=spec.cartridge_id, mount=spec.mount,
            by_id=spec.by_id, source_path=spec.source_path,
        )
        if not readiness['device_serial_registered']:
            raise BackupExecutionError('registered hardware serial required')
        # Reading from the validated registry is important: do not obtain
        # identity solely from parameters supplied by a controller.
        from .cartridges import load_cartridge_registry
        matches = [c for c in load_cartridge_registry(spec.registry)
                   if c.cartridge_id == spec.cartridge_id]
        if len(matches) != 1 or not matches[0].device_serial:
            raise BackupExecutionError('cartridge identity missing')
        c = matches[0]
        self._authorization = DurableHostAuthorizationSession(
            clock=self._clock,
            journal=DurableConfirmationJournal(spec.journal_root),
        )
        digest = readiness['plan_digest']
        self._authorization.arm(
            cartridge_id=c.cartridge_id, cartridge_uuid=c.uuid,
            device_serial=c.device_serial, plan_digest=digest,
        )
        self._preflight = LoadmasterPhysicalPreflight(
            cartridge_id=c.cartridge_id, cartridge_uuid=c.uuid,
            device_serial=c.device_serial, plan_state='READY',
            backup_files=1, backup_bytes=readiness['size_bytes'],
            baseline_verified=True, identity_verified=True,
            backlog_verified=True, plan_digest=digest,
            generated_at_monotonic=self._clock(),
        )
        self._spec = spec
        self._state = 'PREPARED'
        return self._preflight

    def on_confirmation(self, confirmation) -> None:
        if self._state != 'PREPARED':
            raise BackupExecutionError('session not accepting confirmation')
        self._authorization.on_confirmation(confirmation)

    def consume_after_physical_press(self) -> dict[str, Any]:
        if self._state != 'PREPARED':
            raise BackupExecutionError('session cannot consume')
        # Always re-probe before consuming, preventing stale intent from
        # silently passing. The USB remains read-only for this entire phase.
        self._state = 'SPENT'
        fresh = probe_one_episode(
            registry=self._spec.registry, backlog=self._spec.backlog,
            cartridge_id=self._spec.cartridge_id, mount=self._spec.mount,
            by_id=self._spec.by_id, source_path=self._spec.source_path,
        )
        if fresh['plan_digest'] != self._preflight.plan_digest:
            self._authorization.disarm()
            raise BackupExecutionError('transfer intent changed since approval')
        result = self._authorization.consume()
        return {**result, 'state': 'HOST_APPROVAL_EVIDENCE_ONLY',
                'executed': False, 'backup_authorized': False,
                'physical_execution_enabled': False}

    def disarm(self) -> None:
        if self._authorization is not None:
            self._authorization.disarm()
        self._state = 'SPENT'

    def execute_physical(self, *args, **kwargs):
        raise BackupExecutionError('PHYSICAL_EXECUTION_DISABLED')
