"""Governed runtime boundary for passive TrueNAS recovery evidence."""

from __future__ import annotations

import hashlib
import json
import os
import stat
import threading
import time
from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .passive_providers import (
    PASSIVE_METHODS,
    READ_ONLY_METHODS,
    TrueNASProtectionEvidenceProvider,
    TrueNASReplacementInventoryProvider,
)

REQUIRED_ROLES = frozenset(
    {"READONLY_ADMIN", "REPLICATION_TASK_READ", "CLOUD_BACKUP_READ"}
)
MAX_RECEIPT_BYTES = 64 * 1024


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _text(value: Any) -> str:
    return str(value or "").strip()


def _cache_key(method: str, arguments: tuple[Any, ...]) -> str:
    body = json.dumps(
        [method, arguments], sort_keys=True, separators=(",", ":"), default=str
    )
    return hashlib.sha256(body.encode()).hexdigest()


@dataclass
class _CacheEntry:
    value: Any
    observed_at: float
    last_accessed: float


class BoundedTrueNASQueryCache:
    """Bound middleware traffic and optionally reuse short-lived stale evidence."""

    def __init__(
        self,
        delegate: Any,
        *,
        ttl_seconds: float = 60.0,
        stale_if_error_seconds: float = 300.0,
        max_entries: int = 8,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if not 10 <= ttl_seconds <= 900:
            raise ValueError("cache TTL must be between 10 and 900 seconds")
        if not 0 <= stale_if_error_seconds <= 3600:
            raise ValueError("stale-if-error must be between 0 and 3600 seconds")
        if not 1 <= max_entries <= 8:
            raise ValueError("cache may contain between 1 and 8 entries")
        self.delegate = delegate
        self.ttl_seconds = float(ttl_seconds)
        self.stale_if_error_seconds = float(stale_if_error_seconds)
        self.max_entries = max_entries
        self.clock = clock
        self._entries: dict[str, _CacheEntry] = {}
        self._lock = threading.RLock()
        self._delegate_calls = 0
        self._cache_hits = 0
        self._stale_hits = 0
        self._last_source = "none"
        self._last_age_seconds: float | None = None

    def call(self, method: str, *arguments: Any) -> Any:
        if method not in PASSIVE_METHODS:
            raise ValueError(f"TrueNAS method is not passive allowlisted: {method}")
        now = self.clock()
        key = _cache_key(method, arguments)
        with self._lock:
            entry = self._entries.get(key)
            age = now - entry.observed_at if entry else None
            if entry and age is not None and 0 <= age < self.ttl_seconds:
                entry.last_accessed = now
                self._cache_hits += 1
                self._last_source = "cache"
                self._last_age_seconds = age
                return deepcopy(entry.value)

            self._delegate_calls += 1
            try:
                value = self.delegate.call(method, *arguments)
            except (OSError, RuntimeError, TypeError, ValueError, AttributeError):
                value = None
            if value is None and entry and age is not None and (
                0 <= age <= self.ttl_seconds + self.stale_if_error_seconds
            ):
                entry.last_accessed = now
                self._stale_hits += 1
                self._last_source = "stale_cache"
                self._last_age_seconds = age
                return deepcopy(entry.value)
            if value is None:
                self._last_source = "unavailable"
                self._last_age_seconds = age
                return None

            self._entries[key] = _CacheEntry(
                value=deepcopy(value), observed_at=now, last_accessed=now
            )
            while len(self._entries) > self.max_entries:
                oldest = min(
                    self._entries,
                    key=lambda item: self._entries[item].last_accessed,
                )
                del self._entries[oldest]
            self._last_source = "live_read"
            self._last_age_seconds = 0.0
            return deepcopy(value)

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

    def metrics(self) -> dict[str, Any]:
        with self._lock:
            return {
                "ttl_seconds": self.ttl_seconds,
                "stale_if_error_seconds": self.stale_if_error_seconds,
                "max_entries": self.max_entries,
                "entries": len(self._entries),
                "delegate_calls": self._delegate_calls,
                "cache_hits": self._cache_hits,
                "stale_hits": self._stale_hits,
                "last_source": self._last_source,
                "last_age_seconds": self._last_age_seconds,
            }


class TrueNASRoleVerifier:
    """Prove the current API session is read-only and minimally sufficient."""

    def __init__(self, client: Any) -> None:
        self.client = client

    def verify(self) -> dict[str, Any]:
        identity = self.client.call("auth.me")
        privilege = _dict(_dict(identity).get("privilege"))
        roles = sorted({_text(item) for item in _list(privilege.get("roles")) if _text(item)})
        role_set = set(roles)
        forbidden = sorted(
            role
            for role in role_set
            if role in {"FULL_ADMIN", "SHARING_ADMIN", "REPLICATION_ADMIN"}
            or role.endswith("_WRITE")
            or role.endswith("_DELETE")
            or role == "FILESYSTEM_FULL_CONTROL"
        )
        missing = sorted(REQUIRED_ROLES - role_set)
        verified = bool(identity and not forbidden and not missing)
        if not identity:
            reason = "auth.me was unavailable"
        elif forbidden:
            reason = "session includes write-capable or unrestricted roles"
        elif missing:
            reason = "session is missing required read-only roles"
        else:
            reason = "session has the required read-only roles and no write roles"
        return {
            "status": "VERIFIED" if verified else "HOLD",
            "least_privilege_verified": verified,
            "required_roles": sorted(REQUIRED_ROLES),
            "missing_roles": missing,
            "forbidden_roles": forbidden,
            "observed_role_count": len(roles),
            "local_account": _dict(identity).get("local") is True,
            "reason": reason,
            "control_authority": False,
        }


class GovernedRestoreReceiptStore:
    """Read incident receipts from one ownership- and mode-governed directory."""

    def __init__(
        self,
        root: Path | str,
        *,
        expected_uid: int | None = None,
        max_bytes: int = MAX_RECEIPT_BYTES,
    ) -> None:
        self.root = Path(root)
        self.expected_uid = os.geteuid() if expected_uid is None else expected_uid
        self.max_bytes = max_bytes

    def _governance(self) -> tuple[bool, str]:
        try:
            metadata = self.root.lstat()
        except OSError:
            return False, "receipt directory is unavailable"
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
            return False, "receipt root must be a real directory"
        if metadata.st_uid != self.expected_uid:
            return False, "receipt directory owner does not match the runtime"
        if metadata.st_mode & 0o022:
            return False, "receipt directory is group- or world-writable"
        return True, "receipt directory ownership and mode are governed"

    def status(self, *, incident_id: str | None = None) -> dict[str, Any]:
        governed, reason = self._governance()
        present = False
        if governed and incident_id:
            try:
                metadata = self._path(incident_id).lstat()
                present = stat.S_ISREG(metadata.st_mode)
            except OSError:
                present = False
        return {
            "governed": governed,
            "reason": reason,
            "receipt_present": present,
            "max_bytes": self.max_bytes,
            "symlinks_allowed": False,
            "runtime_writes_allowed": False,
        }

    def _path(self, incident_id: str) -> Path:
        name = hashlib.sha256(_text(incident_id).encode()).hexdigest()
        return self.root / f"{name}.json"

    def load(self, *, incident_id: str) -> dict[str, Any] | None:
        governed, _reason = self._governance()
        if not governed:
            return None
        path = self._path(incident_id)
        try:
            metadata = path.lstat()
        except OSError:
            return None
        if (
            stat.S_ISLNK(metadata.st_mode)
            or not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != self.expected_uid
            or metadata.st_mode & 0o022
            or metadata.st_size <= 0
            or metadata.st_size > self.max_bytes
        ):
            return None
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        try:
            descriptor = os.open(path, flags)
            with os.fdopen(descriptor, "rb") as handle:
                confirmed = os.fstat(handle.fileno())
                if (
                    not stat.S_ISREG(confirmed.st_mode)
                    or confirmed.st_uid != self.expected_uid
                    or confirmed.st_mode & 0o022
                    or confirmed.st_size != metadata.st_size
                ):
                    return None
                payload = json.loads(handle.read(self.max_bytes + 1))
        except (OSError, ValueError, json.JSONDecodeError):
            return None
        if not isinstance(payload, dict):
            return None
        if _text(payload.get("incident_id")) != _text(incident_id):
            return None
        return payload


class GovernedPassiveEvidenceRuntime:
    """Fail-closed composition of role, cache, store, and provider gates."""

    def __init__(
        self,
        client: Any,
        receipt_store: GovernedRestoreReceiptStore,
        *,
        candidate_delegate: Any | None = None,
    ) -> None:
        self.client = client
        self.receipt_store = receipt_store
        self.role_verifier = TrueNASRoleVerifier(client)
        self.candidate_delegate = candidate_delegate

    def observe(self, *, incident_id: str) -> dict[str, Any]:
        stale_before = self.client.metrics()["stale_hits"]
        role = self.role_verifier.verify()
        store = self.receipt_store.status(incident_id=incident_id)
        base = {
            "schema_version": 1,
            "provider_id": "truenas-api:governed-runtime",
            "provider_mode": "passive_local",
            "runtime_status": "HOLD",
            "role_verification": role,
            "receipt_store": store,
            "read_only": True,
            "control_authority": False,
            "restore_verified": False,
        }
        if role["least_privilege_verified"] is not True:
            base["hold_reason"] = role["reason"]
            base["cache"] = self.client.metrics()
            return base
        if store["governed"] is not True:
            base["hold_reason"] = store["reason"]
            base["cache"] = self.client.metrics()
            return base

        provider = TrueNASProtectionEvidenceProvider(
            self.client,
            receipt_loader=lambda: self.receipt_store.load(incident_id=incident_id),
        )
        result = provider.observe(incident_id=incident_id)
        cache = self.client.metrics()
        if cache["stale_hits"] > stale_before:
            result.pop("backup_context", None)
            result["restore_verified"] = False
            result["hold_reason"] = (
                "stale cached evidence is display-only and cannot clear recovery"
            )
        result.update(
            {
                "runtime_status": "READY" if result["restore_verified"] else "HOLD",
                "role_verification": role,
                "receipt_store": store,
                "cache": cache,
            }
        )
        return result

    def candidates(
        self,
        original_fault: dict[str, Any],
        *,
        storage_devices: list[dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        if self.candidate_delegate is None:
            return []
        if self.role_verifier.verify()["least_privilege_verified"] is not True:
            return []
        return TrueNASReplacementInventoryProvider(
            self.client, self.candidate_delegate
        ).candidates(original_fault, storage_devices=storage_devices)


__all__ = [
    "BoundedTrueNASQueryCache",
    "GovernedPassiveEvidenceRuntime",
    "GovernedRestoreReceiptStore",
    "REQUIRED_ROLES",
    "TrueNASRoleVerifier",
]
