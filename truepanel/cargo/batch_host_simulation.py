"""Simulation-only GPIO bridge for batch-scoped host evidence.

No real GPIO reader, device mount, or USB write path exists here. A host
integration must separately attest a fresh batch and physical cartridge.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .batch_authorization import BatchApprovalScope, BatchItem
from .backup_executor import BackupExecutionError
from .copy_button import CopyButtonConfirmation, LoadmasterPhysicalPreflight


@dataclass(frozen=True)
class BatchSessionSpec:
    cartridge_id: str
    cartridge_uuid: str
    device_serial: str
    items: tuple[BatchItem, ...]


class SimulatedBatchHostSession:
    """Use the real bridge callback contract with a fake GPIO service.

    The supplied fresh_digest reader models a revalidated inventory and
    must not be interpreted as a physical attestation.
    """

    def __init__(self, *, clock: Callable[[], float],
                 fresh_digest: Callable[[], str]):
        self.clock = clock
        self.fresh_digest = fresh_digest
        self.scope = None
        self.confirmation = None
        self.state = 'NEW'
        self.spec = None

    def prepare(self, spec: BatchSessionSpec) -> LoadmasterPhysicalPreflight:
        if self.state != 'NEW' or not spec.device_serial:
            raise BackupExecutionError('batch session cannot arm')
        self.scope = BatchApprovalScope(
            cartridge_id=spec.cartridge_id, cartridge_uuid=spec.cartridge_uuid,
            items=spec.items)
        self.spec = spec
        self.state = 'PREPARED'
        return LoadmasterPhysicalPreflight(
            cartridge_id=spec.cartridge_id,
            cartridge_uuid=spec.cartridge_uuid,
            device_serial=spec.device_serial, plan_state='READY',
            backup_files=len(spec.items),
            backup_bytes=sum(item.size_bytes for item in spec.items),
            baseline_verified=True, identity_verified=True,
            backlog_verified=True, plan_digest=self.scope.digest,
            generated_at_monotonic=self.clock())

    def on_confirmation(self, confirmation: CopyButtonConfirmation) -> None:
        if self.state != 'PREPARED' or self.confirmation is not None:
            raise BackupExecutionError('batch callback refused')
        if type(confirmation) is not CopyButtonConfirmation:
            raise BackupExecutionError('untrusted confirmation')
        if (confirmation.cartridge_id != self.spec.cartridge_id or
                confirmation.cartridge_uuid != self.spec.cartridge_uuid or
                confirmation.device_serial != self.spec.device_serial or
                confirmation.plan_digest != self.scope.digest):
            raise BackupExecutionError('confirmation scope mismatch')
        age = self.clock() - confirmation.confirmed_at_monotonic
        if not 0 <= age <= 30:
            raise BackupExecutionError('confirmation expired')
        self.confirmation = confirmation

    def consume_after_physical_press(self) -> dict:
        if self.state != 'PREPARED' or self.confirmation is None:
            raise BackupExecutionError('batch confirmation missing')
        self.state = 'SPENT'
        evidence = {
            'state': 'HOST_APPROVAL_EVIDENCE_ONLY',
            'cartridge_id': self.spec.cartridge_id,
            'plan_digest': self.scope.digest,
            'physical_execution_enabled': False, 'executed': False}
        approved = self.scope.consume(
            host_evidence=evidence, fresh_digest=self.fresh_digest())
        return {**evidence, 'batch_items': approved,
                'backup_authorized': False}

    def disarm(self) -> None:
        self.state = 'SPENT'

    def execute_physical(self, *args, **kwargs):
        raise BackupExecutionError('PHYSICAL_EXECUTION_DISABLED')
