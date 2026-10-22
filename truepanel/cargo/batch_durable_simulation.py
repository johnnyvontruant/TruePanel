"""Durable simulated batch host handoff, never physical execution.

This subclass exercises persistence across host session instances.
The journal is consumed before an approval result leaves the bridge.
"""
from __future__ import annotations

from pathlib import Path

from .backup_executor import BackupExecutionError, DurableConfirmationJournal
from .batch_host_simulation import SimulatedBatchHostSession


class DurableSimulatedBatchHostSession(SimulatedBatchHostSession):
    def __init__(self, *, clock, fresh_digest, journal_root: Path):
        super().__init__(clock=clock, fresh_digest=fresh_digest)
        self.journal = DurableConfirmationJournal(journal_root)

    def consume_after_physical_press(self) -> dict:
        if self.state != 'PREPARED' or self.confirmation is None:
            raise BackupExecutionError('batch confirmation missing')
        self.state = 'SPENT'
        # Fresh intent is checked before recording consumption. The journal
        # is still permanently burned before any approval evidence escapes.
        if self.fresh_digest() != self.scope.digest:
            raise BackupExecutionError('batch intent changed before consumption')
        self.journal.consume(cartridge_id=self.spec.cartridge_id,
                             plan_digest=self.scope.digest)
        evidence = {
            'state': 'HOST_APPROVAL_EVIDENCE_ONLY',
            'cartridge_id': self.spec.cartridge_id,
            'plan_digest': self.scope.digest,
            'physical_execution_enabled': False, 'executed': False}
        approved = self.scope.consume(
            host_evidence=evidence, fresh_digest=self.scope.digest)
        return {**evidence, 'batch_items': approved,
                'backup_authorized': False, 'durably_consumed': True}
