"""Crash-safe, replay-safe persistence for verified witness transitions."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Final

from .transparency_witness_continuity import (
    SCHEMA as CONTINUITY_SCHEMA,
)
from .transparency_witness_continuity import (
    STATUS_REHEARSED as CONTINUITY_REHEARSED,
)
from .transparency_witness_continuity import (
    TRANSITION_SCHEMA,
    transition_statement,
)

SCHEMA: Final = "truepanel.aegis-transparency-witness-durable-state/v1"
STATUS_COMMITTED: Final = "WITNESS_STATE_DURABLY_COMMITTED"
STATUS_REPLAYED: Final = "WITNESS_STATE_COMMIT_REPLAYED"
_DENIED: Final = (
    "production_trusted",
    "runtime_authority",
    "deployment_authority",
    "hardware_authority",
    "network_authority",
    "storage_authority",
)
_CRASH_STAGES: Final = (
    "before_temp_write",
    "after_temp_fsync",
    "after_replace",
    "after_directory_fsync",
)


class WitnessStateError(RuntimeError):
    """A durable-state update was rejected without publishing a signature."""


class InjectedCrash(WitnessStateError):
    """Deterministic HoloDeck crash point; never used by the runtime path."""

    def __init__(self, stage: str) -> None:
        super().__init__(f"InjectedCrash:{stage}")
        self.stage = stage


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _record_digest(record: Mapping[str, Any]) -> str:
    return _digest(
        {key: value for key, value in record.items() if key != "record_sha256"}
    )


def _state_identity(state: Mapping[str, Any]) -> tuple[Any, ...]:
    return (
        state.get("monitor_id"),
        state.get("origin"),
        state.get("tree_size"),
        state.get("root_hash_sha256"),
        state.get("checkpoint_sha256"),
        state.get("state_sequence"),
    )


class WitnessDurableStateStore:
    """One-monitor file adapter with serialized compare-and-swap updates.

    The verified transition, response signature, and successor state are one
    content-addressed record.  The record is fsynced, atomically replaced, and
    its directory fsynced before the signature can leave ``commit``.
    """

    def __init__(self, root: Path, monitor_id: str) -> None:
        self.root = Path(root)
        self.monitor_id = monitor_id
        self.path = self.root / "witness-state.json"
        self.pending_path = self.root / ".witness-state.pending"
        self.lock_path = self.root / ".witness-state.lock"

    def initialize(self, state: Mapping[str, Any]) -> dict[str, Any]:
        self._prepare_root()
        with self.lock_path.open("a+b") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            self._discard_uncommitted_pending()
            if self.path.exists():
                return self.read()
            if state.get("monitor_id") != self.monitor_id:
                raise WitnessStateError("WitnessStateIdentityMismatch")
            record: dict[str, Any] = {
                "schema": SCHEMA,
                "monitor_id": self.monitor_id,
                "state": dict(state),
                "previous_record_sha256": None,
                "transition_sha256": None,
                "response_signature": None,
                "publication_state": "GENESIS",
            }
            record["record_sha256"] = _record_digest(record)
            self._atomic_replace(record, None)
            return record

    def read(self) -> dict[str, Any]:
        if self.path.is_symlink() or not self.path.is_file():
            raise WitnessStateError("WitnessStateFileInvalid")
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise WitnessStateError("WitnessStateCorrupt") from error
        if not isinstance(value, dict) or value.get("schema") != SCHEMA:
            raise WitnessStateError("WitnessStateSchemaUnsupported")
        if value.get("monitor_id") != self.monitor_id:
            raise WitnessStateError("WitnessStateIdentityMismatch")
        if value.get("record_sha256") != _record_digest(value):
            raise WitnessStateError("WitnessStateDigestMismatch")
        if not isinstance(value.get("state"), dict):
            raise WitnessStateError("WitnessStatePayloadInvalid")
        return value

    def recover(self) -> dict[str, Any]:
        """Discard an uncommitted temp file and return the committed record."""
        self._prepare_root()
        with self.lock_path.open("a+b") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            pending_discarded = self._discard_uncommitted_pending()
            record = self.read()
            return {
                "record": record,
                "pending_discarded": pending_discarded,
                "recoverable_signature": record.get("response_signature"),
                "publication_state": record.get("publication_state"),
            }

    def commit(
        self,
        continuity: Mapping[str, Any],
        transition: Mapping[str, Any],
        *,
        crash_at: str | None = None,
    ) -> dict[str, Any]:
        """Commit one already-verified transition and only then release its signature."""
        if crash_at is not None and crash_at not in _CRASH_STAGES:
            raise WitnessStateError("WitnessCrashStageInvalid")
        self._prepare_root()
        with self.lock_path.open("a+b") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            self._discard_uncommitted_pending()
            current = self.read()
            self._validate_continuity(continuity, transition)
            before = transition.get("state_before")
            after = transition.get("state_after")
            if not isinstance(before, Mapping) or not isinstance(after, Mapping):
                raise WitnessStateError("WitnessTransitionStateInvalid")
            transition_sha256 = hashlib.sha256(
                transition_statement(transition)
            ).hexdigest()
            signature = transition.get("signature")
            if not isinstance(signature, str) or not signature:
                raise WitnessStateError("WitnessTransitionSignatureRequired")

            if _state_identity(current["state"]) == _state_identity(after):
                if (
                    current.get("transition_sha256") == transition_sha256
                    and current.get("response_signature") == signature
                ):
                    return self._result(STATUS_REPLAYED, current, signature)
                raise WitnessStateError("WitnessCommittedStateConflict")
            if _state_identity(current["state"]) != _state_identity(before):
                raise WitnessStateError("WitnessCompareAndSwapConflict")
            if int(after["state_sequence"]) != int(before["state_sequence"]) + 1:
                raise WitnessStateError("WitnessStateSequenceInvalid")

            record: dict[str, Any] = {
                "schema": SCHEMA,
                "monitor_id": self.monitor_id,
                "state": dict(after),
                "previous_record_sha256": current["record_sha256"],
                "transition_sha256": transition_sha256,
                "response_signature": signature,
                "publication_state": "READY_AFTER_DURABLE_COMMIT",
            }
            record["record_sha256"] = _record_digest(record)
            self._atomic_replace(record, crash_at)
            return self._result(STATUS_COMMITTED, record, signature)

    def _validate_continuity(
        self, continuity: Mapping[str, Any], transition: Mapping[str, Any]
    ) -> None:
        if continuity.get("schema") != CONTINUITY_SCHEMA:
            raise WitnessStateError("WitnessContinuitySchemaUnsupported")
        if continuity.get("status") != CONTINUITY_REHEARSED:
            raise WitnessStateError("WitnessContinuityRequired")
        if self.monitor_id not in continuity.get("valid_monitor_ids", ()):
            raise WitnessStateError("WitnessMonitorNotVerified")
        if any(continuity.get(name) is not False for name in _DENIED):
            raise WitnessStateError("WitnessContinuityAuthorityEscalation")
        if transition.get("schema") != TRANSITION_SCHEMA:
            raise WitnessStateError("WitnessTransitionSchemaUnsupported")
        if transition.get("monitor_id") != self.monitor_id:
            raise WitnessStateError("WitnessTransitionIdentityMismatch")
        after = transition.get("state_after")
        if not isinstance(after, Mapping):
            raise WitnessStateError("WitnessTransitionStateInvalid")
        if continuity.get("current_checkpoint_sha256") != after.get(
            "checkpoint_sha256"
        ):
            raise WitnessStateError("WitnessContinuityCheckpointMismatch")

    def _prepare_root(self) -> None:
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        if self.root.is_symlink() or not self.root.is_dir():
            raise WitnessStateError("WitnessStateRootInvalid")
        os.chmod(self.root, 0o700)

    def _discard_uncommitted_pending(self) -> bool:
        if not self.pending_path.exists():
            return False
        if self.pending_path.is_symlink() or not self.pending_path.is_file():
            raise WitnessStateError("WitnessPendingStateInvalid")
        self.pending_path.unlink()
        self._fsync_directory()
        return True

    def _atomic_replace(self, record: Mapping[str, Any], crash_at: str | None) -> None:
        if crash_at == "before_temp_write":
            raise InjectedCrash(crash_at)
        data = _canonical(record) + b"\n"
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        descriptor = os.open(self.pending_path, flags, 0o600)
        try:
            with os.fdopen(descriptor, "wb", closefd=True) as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
        except BaseException:
            if self.pending_path.exists():
                self.pending_path.unlink()
            raise
        if crash_at == "after_temp_fsync":
            raise InjectedCrash(crash_at)
        os.replace(self.pending_path, self.path)
        if crash_at == "after_replace":
            raise InjectedCrash(crash_at)
        self._fsync_directory()
        if crash_at == "after_directory_fsync":
            raise InjectedCrash(crash_at)

    def _fsync_directory(self) -> None:
        descriptor = os.open(self.root, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    def _result(
        self, status: str, record: Mapping[str, Any], signature: str
    ) -> dict[str, Any]:
        result = {
            "schema": SCHEMA,
            "status": status,
            "monitor_id": self.monitor_id,
            "record_sha256": record["record_sha256"],
            "state_sequence": record["state"]["state_sequence"],
            "response_signature": signature,
            "signature_released_after_durable_commit": True,
            "eligible_for_production_trust": False,
            "active_runtime_record_validation": "PENDING",
            **{name: False for name in _DENIED},
        }
        result["result_sha256"] = _digest(result)
        return result


__all__ = [
    "InjectedCrash",
    "SCHEMA",
    "STATUS_COMMITTED",
    "STATUS_REPLAYED",
    "WitnessDurableStateStore",
    "WitnessStateError",
]
