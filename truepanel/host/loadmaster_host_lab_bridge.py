"""Host polling-service to crash-durable batch integration rehearsal (LAB ONLY).

This adapter wires the *existing* LoadmasterCopyButtonService to the checkpoint-5
journal and resumable transport. Reader and identity providers in tests are fake.
It deliberately requires marked /tmp or /var/tmp roots and cannot change mounts,
read real GPIO, or publish production receipts. Not a physical USB executor.

Safety boundary: a CopyButtonConfirmation dataclass alone is forgeable. We never
expose an endpoint to submit one; the callback is registered only with this
host-owned polling service. Actual production must bind a trusted GPIO reader,
cryptographically/durably attested identity, pinned dirfds, mount supervision.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from truepanel.cargo.copy_button import (
    CopyButtonConfirmation, LoadmasterCopyButtonGate, LoadmasterPhysicalPreflight,
)
from truepanel.cargo.durable_batch_lab import (
    Batch, BatchError, batch_digest, execute_batch, plan_batch,
    read_receipt, reapprove_batch,
)
from truepanel.cargo.resumable_rsync_lab import _lab
from truepanel.host.loadmaster_copy_button import LoadmasterCopyButtonService


@dataclass(frozen=True)
class CartridgeIdentity:
    cartridge_id: str
    filesystem_uuid: str
    device_serial: str


class HostLabBridge:
    """Exactly one in-flight batch, dispatched off the GPIO polling thread."""

    def __init__(self, *, root: Path, reader: object,
                 identity_reader: Callable[[], CartridgeIdentity],
                 event_recorder: Callable[[dict], None] | None = None,
                 clock: Callable[[], float] = time.monotonic,
                 poll_seconds: float = 0.005,
                 debounce_seconds: float = 0.075,
                 confirmation_window_seconds: float = 30.0) -> None:
        _lab(root)  # Does not merely validate a prefix; requires test marker.
        if not callable(identity_reader):
            raise BatchError('identity reader required')
        self._root = root
        self._clock = clock
        self._identity_reader = identity_reader
        self._event_recorder = event_recorder
        self._reader = reader
        self._confirmation_window_seconds = confirmation_window_seconds
        self._armed_at: float | None = None
        self._lock = threading.RLock()
        self._state = 'IDLE'
        self._batch: Batch | None = None
        self._result: dict | None = None
        self._error: str | None = None
        self._worker: threading.Thread | None = None
        self._confirmation_count = 0
        self._closed = False
        gate = LoadmasterCopyButtonGate(
            read_level=reader.read_level,
            clock=clock,
            debounce_seconds=debounce_seconds,
            confirmation_window_seconds=confirmation_window_seconds,
        )
        self._service = LoadmasterCopyButtonService(
            reader=reader, gate=gate,
            on_confirmation=self._on_confirmation,
            event_recorder=self._record,
            poll_seconds=poll_seconds,
        )

    def _record(self, event: dict) -> None:
        if self._event_recorder:
            try:
                self._event_recorder(dict(event))
            except Exception:
                pass  # Recorder failure cannot grant write authority.

    def _assert_identity(self, batch: Batch) -> None:
        _lab(self._root)
        seen = self._identity_reader()
        if not isinstance(seen, CartridgeIdentity) or seen != CartridgeIdentity(
                batch.cartridge_id, batch.cartridge_uuid, batch.device_serial):
            raise BatchError('cartridge identity changed or unreadable')

    def prepare(self, entries: list[tuple[str, str]]) -> Batch:
        """Read-only planning, forbidden while another session remains live."""
        with self._lock:
            if self._closed or self._state in ('ARMED', 'TRANSFERRING'):
                raise BatchError('host session is busy or closed')
            _lab(self._root)
            identity = self._identity_reader()
            if not isinstance(identity, CartridgeIdentity):
                raise BatchError('cartridge identity not verified')
            b = plan_batch(self._root, cartridge_id=identity.cartridge_id,
                           cartridge_uuid=identity.filesystem_uuid,
                           device_serial=identity.device_serial, entries=entries)
            self._assert_identity(b)
            self._batch = b
            self._result = None
            self._error = None
            self._state = 'PREVIEW'
            return b

    def prepare_retry(self, batch: Batch) -> Batch:
        """Use identical immutable action hashes and a fresh nonce."""
        with self._lock:
            if self._closed or self._state in ('ARMED', 'TRANSFERRING'):
                raise BatchError('host session is busy or closed')
            _lab(self._root)
            self._assert_identity(batch)
            b = reapprove_batch(batch)
            self._batch = b
            self._result = None
            self._error = None
            self._state = 'PREVIEW'
            return b

    def arm(self, batch: Batch) -> None:
        """Begin a *fresh* short authorization window, without transferring."""
        with self._lock:
            if self._closed or self._state != 'PREVIEW' or batch is not self._batch:
                raise BatchError('no matching preview or session not idle')
            self._assert_identity(batch)
            if read_receipt(self._root, batch) is not None:
                raise BatchError('approval already consumed')
            # A held-down button must not count as a *new* confirmation.
            level = self._reader.read_level()
            if type(level) not in (int, bool) or int(level) != 1:
                raise BatchError('release physical Copy button before arming')
            preflight = LoadmasterPhysicalPreflight(
                cartridge_id=batch.cartridge_id,
                cartridge_uuid=batch.cartridge_uuid,
                device_serial=batch.device_serial,
                plan_state='READY',
                backup_files=len(batch.actions),
                backup_bytes=sum(a.size for a in batch.actions),
                baseline_verified=True, identity_verified=True,
                backlog_verified=True,
                plan_digest=batch_digest(batch),
                generated_at_monotonic=self._clock(),
            )
            # These flags are valid only for our disposable test lab. Do not
            # use this construction for a real cartridge preflight.
            self._service.arm(preflight)
            self._state = 'ARMED'
            self._armed_at = self._clock()
            self._service.start()
            self._record({'event': 'host_lab_armed', 'digest': batch_digest(batch)})

    def _on_confirmation(self, confirmation: CopyButtonConfirmation) -> None:
        """Called on GPIO polling thread: enqueue ONLY, never run rsync here."""
        with self._lock:
            self._confirmation_count += 1
            batch = self._batch
            if (self._closed or self._state != 'ARMED' or batch is None
                or confirmation.plan_digest != batch_digest(batch)):
                self._record({'event': 'host_lab_confirmation_rejected'})
                return
            # The durable executor rechecks the whole confirmation and writes
            # an exclusive consumed record *before* it can invoke rsync.
            self._state = 'TRANSFERRING'
            self._worker = threading.Thread(
                target=self._run_batch,
                args=(batch, confirmation),
                daemon=True, name='loadmaster-lab-batch',
            )
            self._worker.start()

    def _run_batch(self, batch: Batch, confirmation: CopyButtonConfirmation) -> None:
        try:
            result = execute_batch(
                self._root, batch, confirmation, clock=self._clock,
                verify_environment=lambda: self._assert_identity(batch),
            )
        except Exception as error:
            with self._lock:
                self._error = f'{type(error).__name__}: {error}'
                self._state = 'FAILED'
            self._record({'event': 'host_lab_failed', 'error': type(error).__name__})
        else:
            with self._lock:
                self._result = result
                self._state = 'COMPLETE'
            self._record({'event': 'host_lab_complete', 'verified': len(result['verified'])})

    def status(self) -> dict:
        with self._lock:
            if self._state == 'ARMED':
                if (self._armed_at is not None and
                    self._clock() - self._armed_at > self._confirmation_window_seconds):
                    self._service.disarm(reason='expired')
                    self._state = 'EXPIRED'
                elif not self._service.snapshot().get('armed', False):
                    self._state = 'EXPIRED'
            return {'state': self._state,
                    'batch_digest': batch_digest(self._batch) if self._batch else None,
                    'confirmed_events': self._confirmation_count,
                    'verified_files': len(self._result['verified']) if self._result else 0,
                    'error': self._error, 'sandbox_only': True}

    def wait(self, timeout: float = 10.0) -> dict:
        """Wait for a worker, never grant or extend an approval."""
        with self._lock:
            worker = self._worker
        if worker is not None:
            worker.join(timeout=timeout)
        return self.status()

    def close(self) -> None:
        with self._lock:
            self._closed = True
            self._service.disarm(reason='lab_closed')
        self._service.stop()
        with self._lock:
            worker = self._worker
        if worker is not None:
            worker.join()  # Do not abandon an active lab rsync worker.
        self._record({'event': 'host_lab_closed'})
