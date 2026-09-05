"""Read-only TrueNAS evidence adapters for AEGIS recovery clearance.

The adapters consume only documented query methods.  They never run, restore,
wipe, replace, offline, or otherwise mutate a TrueNAS system.  A successful
backup task is recorded as protection coverage, not promoted to restore proof;
that promotion requires a separate digest-intact verification receipt.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from collections.abc import Callable
from typing import Any

READ_ONLY_METHODS = frozenset(
    {"disk.query", "replication.query", "cloud_backup.query"}
)
PASSIVE_METHODS = READ_ONLY_METHODS | {"auth.me", "system.version"}
RESTORE_RECEIPT_SCHEMA = "truepanel.restore-verification/v1"
SUCCESSFUL_TASK_STATES = frozenset({"SUCCESS", "FINISHED"})


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _text(value: Any) -> str:
    return str(value or "").strip()


def _integer(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _digest(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def issue_restore_verification_receipt(
    *,
    incident_id: str,
    method: str,
    task_id: int,
    scope: str,
    restore_test_id: str,
    verified_at: float,
    objects_verified: int,
) -> dict[str, Any]:
    """Build a deterministic fixture-compatible external verification receipt."""

    receipt = {
        "schema": RESTORE_RECEIPT_SCHEMA,
        "incident_id": _text(incident_id),
        "method": _text(method),
        "task_id": task_id,
        "scope": _text(scope),
        "restore_test_id": _text(restore_test_id),
        "verified_at": verified_at,
        "result": "PASS",
        "objects_verified": objects_verified,
        "read_only_observation": True,
        "control_authority": False,
    }
    receipt["evidence_sha256"] = _digest(receipt)
    return receipt


class TrueNASReadOnlyQueryClient:
    """Small allowlisted adapter over the local TrueNAS middleware CLI."""

    def __init__(
        self,
        *,
        runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
        executable: str | None = None,
    ) -> None:
        self._runner = runner or subprocess.run
        self._executable = executable

    def query(
        self,
        method: str,
        *,
        filters: list[Any] | None = None,
        options: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        if method not in READ_ONLY_METHODS:
            raise ValueError(f"TrueNAS method is not read-only allowlisted: {method}")
        payload = self.call(method, filters or [], options or {})
        return [dict(item) for item in _list(payload) if isinstance(item, dict)]

    def call(self, method: str, *arguments: Any) -> Any:
        """Call one passive method and return decoded JSON or ``None``."""

        if method not in PASSIVE_METHODS:
            raise ValueError(f"TrueNAS method is not passive allowlisted: {method}")
        executable = self._executable or shutil.which("midclt")
        if not executable:
            return None
        command = [executable, "call", method]
        command.extend(
            json.dumps(argument, separators=(",", ":")) for argument in arguments
        )
        try:
            result = self._runner(
                command,
                check=False,
                capture_output=True,
                text=True,
                timeout=10.0,
            )
        except (OSError, subprocess.SubprocessError):
            return None
        if result.returncode != 0:
            return None
        try:
            return json.loads(result.stdout)
        except (TypeError, json.JSONDecodeError):
            return None


def _task_state(task: dict[str, Any]) -> str:
    state = task.get("state")
    if isinstance(state, dict):
        state = state.get("state") or state.get("status")
    if not state:
        job = _dict(task.get("job"))
        state = job.get("state") or job.get("status")
    return _text(state).upper()


def _task_succeeded(task: dict[str, Any]) -> bool:
    return task.get("enabled") is True and task.get("state") in SUCCESSFUL_TASK_STATES


class TrueNASProtectionEvidenceProvider:
    """Observe backup tasks and admit only separately verified restores."""

    def __init__(
        self,
        client: TrueNASReadOnlyQueryClient,
        *,
        receipt_loader: Callable[[], dict[str, Any] | None] | None = None,
    ) -> None:
        self.client = client
        self.receipt_loader = receipt_loader or (lambda: None)

    def observe(self, *, incident_id: str) -> dict[str, Any]:
        tasks: list[dict[str, Any]] = []
        for method in ("replication.query", "cloud_backup.query"):
            for task in self.client.query(method):
                tasks.append(
                    {
                        "method": method,
                        "task_id": task.get("id"),
                        "name": task.get("name") or task.get("description"),
                        "scope": task.get("path")
                        or (_list(task.get("source_datasets")) or [None])[0],
                        "enabled": task.get("enabled") is True,
                        "state": _task_state(task) or "UNKNOWN",
                    }
                )

        observation = {
            "schema_version": 1,
            "provider_id": "truenas-api:data-protection",
            "provider_mode": "passive_local",
            "read_only": True,
            "control_authority": False,
            "tasks": tasks,
            "successful_tasks": sum(1 for item in tasks if _task_succeeded(item)),
            "restore_verified": False,
            "hold_reason": "backup task success is not a tested restore",
        }
        receipt = self.receipt_loader()
        if not isinstance(receipt, dict):
            return observation

        unsigned = dict(receipt)
        actual_digest = _text(unsigned.pop("evidence_sha256", "")).lower()
        method = _text(receipt.get("method"))
        task_id = receipt.get("task_id")
        matching = [
            item
            for item in tasks
            if item["method"] == method
            and item["task_id"] == task_id
            and _task_succeeded(item)
        ]
        valid = bool(
            receipt.get("schema") == RESTORE_RECEIPT_SCHEMA
            and _text(receipt.get("incident_id")) == _text(incident_id)
            and method in {"replication.query", "cloud_backup.query"}
            and isinstance(task_id, int)
            and len(matching) == 1
            and _text(receipt.get("scope"))
            and _text(matching[0].get("scope")) == _text(receipt.get("scope"))
            and _text(receipt.get("restore_test_id"))
            and receipt.get("result") == "PASS"
            and (_integer(receipt.get("objects_verified")) or 0) > 0
            and receipt.get("read_only_observation") is True
            and receipt.get("control_authority") is False
            and actual_digest == _digest(unsigned)
        )
        if not valid:
            observation["hold_reason"] = "restore verification receipt is invalid"
            return observation

        observation.update(
            {
                "restore_verified": True,
                "hold_reason": None,
                "backup_context": {
                    "incident_id": incident_id,
                    "independent_backup_confirmed": True,
                    "restore_tested": True,
                    "restore_test_id": receipt["restore_test_id"],
                    "scope": receipt["scope"],
                    "source": f"TrueNAS {method} task {task_id}",
                    "verified_at": receipt["verified_at"],
                    "provider_id": "truenas-api:restore-verification",
                    "provider_mode": "passive_local",
                    "evidence_reference": (
                        f"{method}:{task_id}:{receipt['restore_test_id']}"
                    ),
                    "evidence_maturity": "governed_restore_receipt",
                    "evidence_sha256": actual_digest,
                },
            }
        )
        return observation


class TrueNASReplacementInventoryProvider:
    """Cross-check local candidates with documented ``disk.query`` evidence."""

    def __init__(self, client: TrueNASReadOnlyQueryClient, delegate: Any) -> None:
        self.client = client
        self.delegate = delegate

    def candidates(
        self,
        original_fault: dict[str, Any],
        *,
        storage_devices: list[dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        local = self.delegate.candidates(
            original_fault,
            storage_devices=storage_devices,
        )
        api_disks = self.client.query(
            "disk.query",
            options={"extra": {"pools": True}},
        )
        by_name = {
            _text(item.get("name") or item.get("devname")): item
            for item in api_disks
            if _text(item.get("name") or item.get("devname"))
        }
        results = []
        for candidate in local:
            item = by_name.get(_text(candidate.get("device")))
            if not item:
                continue
            serial = _text(item.get("serial"))
            size = _integer(item.get("size"))
            identifier = _text(item.get("identifier"))
            local_model = _text(candidate.get("model"))
            api_model = _text(item.get("model"))
            if not (
                identifier
                and serial
                and serial.endswith(_text(candidate.get("serial_last4")))
                and (not local_model or local_model == api_model)
                and size == _integer(candidate.get("capacity_bytes"))
                and item.get("pool") in {None, ""}
                and candidate.get("contains_preserved_data") is False
                and candidate.get("member_of_pool") is False
            ):
                continue
            enriched = dict(candidate)
            enriched.update(
                {
                    "provider_id": "truenas-api:disk.query",
                    "provider_mode": "passive_local",
                    "evidence_reference": f"disk.query:{identifier}",
                    "evidence_maturity": "passive_api_cross_check",
                    "identity_sha256": _digest(
                        {
                            "identifier": identifier,
                            "serial": serial,
                            "model": item.get("model"),
                            "size": size,
                        }
                    ),
                }
            )
            results.append(enriched)
        return results


__all__ = [
    "PASSIVE_METHODS",
    "READ_ONLY_METHODS",
    "TrueNASProtectionEvidenceProvider",
    "TrueNASReadOnlyQueryClient",
    "TrueNASReplacementInventoryProvider",
    "issue_restore_verification_receipt",
]
