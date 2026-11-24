"""SQLite-backed, process-crash-recoverable witness state adapters."""

from __future__ import annotations

import hashlib
import json
import os
import signal
import sqlite3
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final

from .transparency_witness_continuity import (
    SCHEMA as CONTINUITY_SCHEMA,
)
from .transparency_witness_continuity import (
    STATUS_REHEARSED as CONTINUITY_REHEARSED,
)
from .transparency_witness_continuity import TRANSITION_SCHEMA, transition_statement
from .transparency_witness_crash_recovery import (
    SCHEMA as RECORD_SCHEMA,
)
from .transparency_witness_crash_recovery import (
    STATUS_COMMITTED,
    STATUS_REPLAYED,
    WitnessStateError,
    _canonical,
    _digest,
    _record_digest,
    _state_identity,
)

SCHEMA: Final = "truepanel.aegis-transparency-witness-sqlite-recovery/v1"
QUORUM_SCHEMA: Final = "truepanel.aegis-isolated-witness-store-quorum/v1"
STATUS_REHEARSED: Final = "ISOLATED_WITNESS_SQLITE_RECOVERY_REHEARSED"
STATUS_HOLD: Final = "ISOLATED_WITNESS_SQLITE_RECOVERY_HOLD"
_DENIED: Final = (
    "production_trusted",
    "runtime_authority",
    "deployment_authority",
    "hardware_authority",
    "network_authority",
    "storage_authority",
)
_HALT_STAGES: Final = (
    "before_begin",
    "after_begin",
    "after_write_before_commit",
    "after_commit_before_response",
)


class SQLiteWitnessDurableStateStore:
    """One-monitor SQLite store with transactional predecessor comparison.

    The standard-library SQLite engine is configured for WAL journaling and
    ``synchronous=FULL``. Test-only process halts are opt-in and terminate only
    the disposable HoloDeck child process that called ``commit``.
    """

    def __init__(
        self,
        root: Path,
        monitor_id: str,
        *,
        allow_test_process_halt: bool = False,
    ) -> None:
        self.root = Path(root)
        self.monitor_id = monitor_id
        self.path = self.root / "witness-state.sqlite3"
        self.allow_test_process_halt = allow_test_process_halt

    def initialize(self, state: Mapping[str, Any]) -> dict[str, Any]:
        if state.get("monitor_id") != self.monitor_id:
            raise WitnessStateError("WitnessStateIdentityMismatch")
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            configured = connection.execute(
                "SELECT monitor_id FROM store_identity WHERE singleton = 1"
            ).fetchone()
            if configured is not None and configured[0] != self.monitor_id:
                raise WitnessStateError("WitnessStoreIdentityMismatch")
            connection.execute(
                "INSERT OR IGNORE INTO store_identity(singleton, monitor_id) "
                "VALUES (1, ?)",
                (self.monitor_id,),
            )
            existing = self._read_row(connection)
            if existing is not None:
                if _state_identity(existing["state"]) != _state_identity(state):
                    raise WitnessStateError("WitnessGenesisStateConflict")
                connection.commit()
                return existing
            record: dict[str, Any] = {
                "schema": RECORD_SCHEMA,
                "monitor_id": self.monitor_id,
                "state": dict(state),
                "previous_record_sha256": None,
                "transition_sha256": None,
                "response_signature": None,
                "publication_state": "GENESIS",
            }
            record["record_sha256"] = _record_digest(record)
            self._insert_record(connection, record)
            connection.commit()
            return record
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()
            self._secure_files()

    def read(self) -> dict[str, Any]:
        connection = self._connect()
        try:
            record = self._read_row(connection)
            if record is None:
                raise WitnessStateError("WitnessStateMissing")
            return record
        finally:
            connection.close()
            self._secure_files()

    def recover(self) -> dict[str, Any]:
        connection = self._connect()
        try:
            integrity = connection.execute("PRAGMA integrity_check").fetchone()
            if integrity is None or integrity[0] != "ok":
                raise WitnessStateError("WitnessSQLiteIntegrityCheckFailed")
            record = self._read_row(connection)
            if record is None:
                raise WitnessStateError("WitnessStateMissing")
            settings = self._settings(connection)
            return {
                "schema": SCHEMA,
                "record": record,
                "recoverable_signature": record.get("response_signature"),
                "publication_state": record.get("publication_state"),
                "integrity_check": "ok",
                "sqlite_settings": settings,
                "process_crash_recovery_rehearsed": True,
                "physical_power_loss_validated": False,
                **{name: False for name in _DENIED},
            }
        finally:
            connection.close()
            self._secure_files()

    def commit(
        self,
        continuity: Mapping[str, Any],
        transition: Mapping[str, Any],
        *,
        test_halt_at: str | None = None,
    ) -> dict[str, Any]:
        if test_halt_at is not None:
            if not self.allow_test_process_halt:
                raise WitnessStateError("WitnessTestProcessHaltNotAllowed")
            if test_halt_at not in _HALT_STAGES:
                raise WitnessStateError("WitnessTestProcessHaltStageInvalid")
        self._validate_continuity(continuity, transition)
        before = transition.get("state_before")
        after = transition.get("state_after")
        if not isinstance(before, Mapping) or not isinstance(after, Mapping):
            raise WitnessStateError("WitnessTransitionStateInvalid")
        signature = transition.get("signature")
        if not isinstance(signature, str) or not signature:
            raise WitnessStateError("WitnessTransitionSignatureRequired")
        transition_sha256 = hashlib.sha256(transition_statement(transition)).hexdigest()

        self._halt(test_halt_at, "before_begin")
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            self._halt(test_halt_at, "after_begin")
            current = self._read_row(connection)
            if current is None:
                raise WitnessStateError("WitnessStateMissing")
            if _state_identity(current["state"]) == _state_identity(after):
                if (
                    current.get("transition_sha256") == transition_sha256
                    and current.get("response_signature") == signature
                ):
                    connection.commit()
                    return self._result(STATUS_REPLAYED, current, signature)
                raise WitnessStateError("WitnessCommittedStateConflict")
            if _state_identity(current["state"]) != _state_identity(before):
                raise WitnessStateError("WitnessCompareAndSwapConflict")
            if int(after["state_sequence"]) != int(before["state_sequence"]) + 1:
                raise WitnessStateError("WitnessStateSequenceInvalid")
            record: dict[str, Any] = {
                "schema": RECORD_SCHEMA,
                "monitor_id": self.monitor_id,
                "state": dict(after),
                "previous_record_sha256": current["record_sha256"],
                "transition_sha256": transition_sha256,
                "response_signature": signature,
                "publication_state": "READY_AFTER_DURABLE_COMMIT",
            }
            record["record_sha256"] = _record_digest(record)
            cursor = connection.execute(
                "UPDATE witness_state SET record_json = ?, record_sha256 = ?, "
                "state_sequence = ? WHERE monitor_id = ? AND record_sha256 = ?",
                (
                    _canonical(record),
                    record["record_sha256"],
                    int(after["state_sequence"]),
                    self.monitor_id,
                    current["record_sha256"],
                ),
            )
            if cursor.rowcount != 1:
                raise WitnessStateError("WitnessCompareAndSwapConflict")
            self._halt(test_halt_at, "after_write_before_commit")
            connection.commit()
            self._secure_files()
            self._halt(test_halt_at, "after_commit_before_response")
            return self._result(STATUS_COMMITTED, record, signature)
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()
            self._secure_files()

    def _prepare_root(self) -> None:
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        if self.root.is_symlink() or not self.root.is_dir():
            raise WitnessStateError("WitnessStateRootInvalid")
        if self.path.is_symlink():
            raise WitnessStateError("WitnessSQLitePathInvalid")
        os.chmod(self.root, 0o700)

    def _connect(self) -> sqlite3.Connection:
        self._prepare_root()
        connection = sqlite3.connect(self.path, timeout=1.0, isolation_level=None)
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=FULL")
        connection.execute("PRAGMA busy_timeout=1000")
        connection.execute("PRAGMA foreign_keys=ON")
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS store_identity (
                singleton INTEGER PRIMARY KEY CHECK(singleton = 1),
                monitor_id TEXT NOT NULL UNIQUE
            );
            CREATE TABLE IF NOT EXISTS witness_state (
                monitor_id TEXT PRIMARY KEY,
                record_json BLOB NOT NULL,
                record_sha256 TEXT NOT NULL,
                state_sequence INTEGER NOT NULL
            );
            """
        )
        self._secure_files()
        return connection

    def _read_row(self, connection: sqlite3.Connection) -> dict[str, Any] | None:
        row = connection.execute(
            "SELECT record_json, record_sha256 FROM witness_state "
            "WHERE monitor_id = ?",
            (self.monitor_id,),
        ).fetchone()
        if row is None:
            return None
        try:
            record = json.loads(bytes(row[0]).decode("utf-8"))
        except (TypeError, UnicodeError, ValueError) as error:
            raise WitnessStateError("WitnessStateCorrupt") from error
        if not isinstance(record, dict) or record.get("schema") != RECORD_SCHEMA:
            raise WitnessStateError("WitnessStateSchemaUnsupported")
        if record.get("monitor_id") != self.monitor_id:
            raise WitnessStateError("WitnessStateIdentityMismatch")
        if row[1] != record.get("record_sha256"):
            raise WitnessStateError("WitnessStateIndexDigestMismatch")
        if record.get("record_sha256") != _record_digest(record):
            raise WitnessStateError("WitnessStateDigestMismatch")
        if not isinstance(record.get("state"), dict):
            raise WitnessStateError("WitnessStatePayloadInvalid")
        return record

    def _insert_record(
        self, connection: sqlite3.Connection, record: Mapping[str, Any]
    ) -> None:
        connection.execute(
            "INSERT INTO witness_state(monitor_id, record_json, record_sha256, "
            "state_sequence) VALUES (?, ?, ?, ?)",
            (
                self.monitor_id,
                _canonical(record),
                record["record_sha256"],
                int(record["state"]["state_sequence"]),
            ),
        )

    def _settings(self, connection: sqlite3.Connection) -> dict[str, Any]:
        journal = connection.execute("PRAGMA journal_mode").fetchone()[0]
        synchronous = connection.execute("PRAGMA synchronous").fetchone()[0]
        return {
            "journal_mode": str(journal).upper(),
            "synchronous": int(synchronous),
            "busy_timeout_ms": int(
                connection.execute("PRAGMA busy_timeout").fetchone()[0]
            ),
        }

    def _secure_files(self) -> None:
        for path in self.root.glob(f"{self.path.name}*"):
            if path.is_file() and not path.is_symlink():
                os.chmod(path, 0o600)

    def _halt(self, requested: str | None, stage: str) -> None:
        if requested == stage:
            os.kill(os.getpid(), signal.SIGKILL)

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
            "signature_released_after_sqlite_commit": True,
            "sqlite_journal_mode": "WAL",
            "sqlite_synchronous": "FULL",
            "eligible_for_production_trust": False,
            "active_runtime_record_validation": "PENDING",
            **{name: False for name in _DENIED},
        }
        result["result_sha256"] = _digest(result)
        return result


def evaluate_isolated_witness_stores(
    stores: Sequence[SQLiteWitnessDurableStateStore],
) -> dict[str, Any]:
    """Require two isolated, healthy stores to agree on one checkpoint."""
    errors: list[str] = []
    observations: list[dict[str, Any]] = []
    if len(stores) != 2:
        errors.append("ExactlyTwoWitnessStoresRequired")
    if len({store.monitor_id for store in stores}) != len(stores):
        errors.append("WitnessStoreIdentityDuplicate")
    if len({store.path.resolve() for store in stores}) != len(stores):
        errors.append("WitnessStorePathNotIsolated")
    for store in stores:
        try:
            recovered = store.recover()
            record = recovered["record"]
            if record.get("publication_state") != "READY_AFTER_DURABLE_COMMIT":
                errors.append("WitnessStoreCommitNotReady")
            if not recovered.get("recoverable_signature"):
                errors.append("WitnessStoreSignatureMissing")
            observations.append(
                {
                    "monitor_id": store.monitor_id,
                    "path_isolated": True,
                    "record_sha256": record["record_sha256"],
                    "checkpoint_sha256": record["state"]["checkpoint_sha256"],
                    "state_sequence": record["state"]["state_sequence"],
                    "integrity_check": recovered["integrity_check"],
                }
            )
        except (OSError, sqlite3.DatabaseError, WitnessStateError):
            errors.append("WitnessStoreRecoveryFailed")
    checkpoints = {item["checkpoint_sha256"] for item in observations}
    sequences = {item["state_sequence"] for item in observations}
    if len(checkpoints) > 1 or len(sequences) > 1:
        errors.append("WitnessStoreCheckpointDisagreement")
    status = STATUS_REHEARSED if not errors and len(observations) == 2 else STATUS_HOLD
    result = {
        "schema": QUORUM_SCHEMA,
        "status": status,
        "stores": observations,
        "store_count": len(observations),
        "isolated_store_paths": len({store.path.resolve() for store in stores}),
        "checkpoint_agreement": len(checkpoints) == 1 and len(observations) == 2,
        "process_crash_recovery_rehearsed": status == STATUS_REHEARSED,
        "physical_power_loss_validated": False,
        "independent_production_monitor_operators": 0,
        "active_runtime_record_validation": "PENDING",
        "eligible_for_production_trust": False,
        "errors": list(dict.fromkeys(errors)),
        **{name: False for name in _DENIED},
    }
    result["result_sha256"] = _digest(result)
    return result


__all__ = [
    "QUORUM_SCHEMA",
    "SCHEMA",
    "STATUS_HOLD",
    "STATUS_REHEARSED",
    "SQLiteWitnessDurableStateStore",
    "evaluate_isolated_witness_stores",
]
