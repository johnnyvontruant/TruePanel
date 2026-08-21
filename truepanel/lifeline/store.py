"""Persistent, metadata-only Project Lifeline repair session ledger.

The ledger remembers the identity and progress of an operator repair across
changing telemetry and Mission Control refreshes.  It writes only TruePanel
metadata.  It has no pool, disk, enclosure, or hardware-control authority.
"""

from __future__ import annotations

import json
import os
import threading
import time
from copy import deepcopy
from pathlib import Path
from typing import Any

from .session import evaluate_drive_repair


DEFAULT_LIFELINE_PATH = Path("/var/lib/truepanel/lifeline/sessions.json")
_SCHEMA_VERSION = 1
_REQUIRED_HEALTHY_OBSERVATIONS = 3
_ALLOWED_ACKNOWLEDGEMENTS = {"backup_state"}


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _text(value: Any) -> str:
    return str(value or "").strip()


def _session_key(evidence: dict[str, Any]) -> str | None:
    pool = _text(evidence.get("pool"))
    vdev = _text(evidence.get("vdev"))
    device = _text(evidence.get("device"))
    if not pool or not vdev or not device:
        return None
    return f"drive:{pool}:{vdev}:{device}"


def _pool_state(payload: dict[str, Any], pool_name: str) -> str:
    storage = _dict(payload.get("storage"))
    for pool in _list(storage.get("pools")):
        if not isinstance(pool, dict):
            continue
        if _text(pool.get("name")) != pool_name:
            continue
        return _text(pool.get("health") or pool.get("state")).upper()
    return ""


def _resilver_running(payload: dict[str, Any]) -> bool:
    storage = _dict(payload.get("storage"))
    activity = _dict(storage.get("zfs_activity"))
    return bool(activity.get("resilver_running", False))


class LifelineSessionStore:
    """Persist repair-session metadata and enrich Mission Control snapshots."""

    def __init__(self, path=None, *, clock=None) -> None:
        self.path = Path(path or DEFAULT_LIFELINE_PATH)
        self.clock = clock or time.time
        self._lock = threading.RLock()
        self._state = self._load()

    def _empty(self) -> dict[str, Any]:
        return {
            "schema_version": _SCHEMA_VERSION,
            "sessions": {},
        }

    def _load(self) -> dict[str, Any]:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return self._empty()
        if not isinstance(raw, dict) or raw.get("schema_version") != _SCHEMA_VERSION:
            return self._empty()
        if not isinstance(raw.get("sessions"), dict):
            raw["sessions"] = {}
        return raw

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(f".{self.path.name}.tmp-{os.getpid()}")
        encoded = json.dumps(
            self._state,
            sort_keys=True,
            indent=2,
        ) + "\n"
        try:
            temporary.write_text(encoded, encoding="utf-8")
            os.chmod(temporary, 0o600)
            os.replace(temporary, self.path)
        finally:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            sessions = list(self._state["sessions"].values())
            sessions.sort(key=lambda item: float(item.get("created_at", 0.0)))
            return {
                "schema_version": _SCHEMA_VERSION,
                "read_only_hardware": True,
                "sessions": deepcopy(sessions),
            }

    def acknowledge(self, session_id: str, acknowledgement: str, value=True) -> dict[str, Any]:
        if acknowledgement not in _ALLOWED_ACKNOWLEDGEMENTS:
            raise ValueError("unsupported Lifeline acknowledgement")
        with self._lock:
            session = self._state["sessions"].get(str(session_id))
            if not isinstance(session, dict):
                raise KeyError("unknown Lifeline session")
            context = session.setdefault("context", {})
            acknowledgements = context.setdefault("acknowledgements", {})
            acknowledgements[acknowledgement] = bool(value)
            session["updated_at"] = float(self.clock())
            self._save()
            return deepcopy(session)

    def set_service_procedure_verified(
        self,
        session_id: str,
        *,
        verified: bool,
        profile: str | None = None,
        source: str | None = None,
    ) -> dict[str, Any]:
        """Record system-verified chassis procedure provenance.

        This is intentionally not an operator acknowledgement. A caller must
        supply the hardware-profile verification result and provenance.
        """

        with self._lock:
            session = self._state["sessions"].get(str(session_id))
            if not isinstance(session, dict):
                raise KeyError("unknown Lifeline session")
            context = session.setdefault("context", {})
            context["service_procedure_verified"] = bool(verified)
            context["service_profile"] = _text(profile) or None
            context["service_source"] = _text(source) or None
            session["updated_at"] = float(self.clock())
            self._save()
            return deepcopy(session)

    def set_replacement_candidates(
        self,
        session_id: str,
        candidates: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Record candidates produced by a read-only inventory validator."""

        safe = [deepcopy(item) for item in candidates if isinstance(item, dict)]
        with self._lock:
            session = self._state["sessions"].get(str(session_id))
            if not isinstance(session, dict):
                raise KeyError("unknown Lifeline session")
            context = session.setdefault("context", {})
            context["replacement_candidates"] = safe
            session["updated_at"] = float(self.clock())
            self._save()
            return deepcopy(session)

    def _new_session(self, key: str, evidence: dict[str, Any]) -> dict[str, Any]:
        now = float(self.clock())
        original = {
            "pool": evidence.get("pool"),
            "vdev": evidence.get("vdev"),
            "vdev_topology": evidence.get("vdev_topology"),
            "remaining_redundancy": evidence.get("remaining_redundancy"),
            "device": evidence.get("device"),
            "bay": evidence.get("bay"),
            "model": evidence.get("model"),
            "serial_last4": evidence.get("serial_last4"),
            "capacity_bytes": evidence.get("capacity_bytes"),
        }
        return {
            "id": key,
            "kind": "drive_replacement",
            "status": "active",
            "created_at": now,
            "updated_at": now,
            "original_fault": original,
            "context": {
                "service_procedure_verified": False,
                "service_profile": None,
                "service_source": None,
                "acknowledgements": {
                    "backup_state": False,
                },
                "replacement_candidates": [],
            },
            "healthy_observations": 0,
            "last_session": None,
        }

    def _evaluate(
        self,
        ledger: dict[str, Any],
        evidence: dict[str, Any],
    ) -> dict[str, Any]:
        context = _dict(ledger.get("context"))
        acknowledgements = _dict(context.get("acknowledgements"))
        candidates = _list(context.get("replacement_candidates"))
        selected = [
            item for item in candidates
            if isinstance(item, dict) and item.get("selected") is True
        ]
        candidate = selected[0] if len(selected) == 1 else None
        if candidate is None and len(candidates) == 1 and isinstance(candidates[0], dict):
            candidate = candidates[0]
        if candidate is None and len(candidates) > 1:
            candidate = {"ambiguous": True}

        repair = evaluate_drive_repair(
            evidence,
            service_procedure_verified=bool(
                context.get("service_procedure_verified", False)
            ),
            backup_acknowledged=bool(
                acknowledgements.get("backup_state", False)
            ),
            replacement_candidate=candidate,
            replacement_operation_confirmed=False,
        )
        return repair.to_payload()

    def observe(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Observe one status payload and return it with persistent Lifeline state."""

        result = deepcopy(payload)
        guidance = _list(result.get("operator_guidance"))
        now = float(self.clock())
        changed = False
        seen: set[str] = set()

        with self._lock:
            sessions = self._state["sessions"]

            for item in guidance:
                if not isinstance(item, dict) or item.get("code") != "storage.disk_faulted":
                    continue
                runtime = _dict(item.get("runtime"))
                evidence = _dict(runtime.get("evidence"))
                key = _session_key(evidence)
                if key is None:
                    continue
                seen.add(key)
                ledger = sessions.get(key)
                if not isinstance(ledger, dict) or ledger.get("status") == "completed":
                    ledger = self._new_session(key, evidence)
                    sessions[key] = ledger
                    changed = True

                ledger["healthy_observations"] = 0
                ledger["updated_at"] = now
                repair = self._evaluate(ledger, evidence)
                if ledger.get("last_session") != repair:
                    ledger["last_session"] = repair
                    changed = True
                item["repair_session"] = deepcopy(repair)

            for key, ledger in list(sessions.items()):
                if not isinstance(ledger, dict) or ledger.get("status") != "active":
                    continue
                if key in seen:
                    continue

                original = _dict(ledger.get("original_fault"))
                pool_name = _text(original.get("pool"))
                pool_state = _pool_state(result, pool_name)
                resilver = _resilver_running(result)

                if pool_state == "ONLINE" and not resilver:
                    healthy = int(ledger.get("healthy_observations", 0)) + 1
                    ledger["healthy_observations"] = healthy
                    changed = True
                    evidence = dict(original)
                    evidence.update(
                        {
                            "pool_state": "ONLINE",
                            "replacement_zfs_state": "ONLINE",
                            "recovery_verified": (
                                healthy >= _REQUIRED_HEALTHY_OBSERVATIONS
                            ),
                            "resilver_state": {
                                "resilver_running": False,
                            },
                        }
                    )
                    repair = self._evaluate(ledger, evidence)
                    ledger["last_session"] = repair
                    ledger["updated_at"] = now
                    if healthy >= _REQUIRED_HEALTHY_OBSERVATIONS:
                        ledger["status"] = "completed"
                        ledger["completed_at"] = now
                else:
                    if ledger.get("healthy_observations") != 0:
                        ledger["healthy_observations"] = 0
                        changed = True
                    ledger["updated_at"] = now

            if changed:
                self._save()

            result["lifeline"] = self.snapshot()
            return result


__all__ = ["DEFAULT_LIFELINE_PATH", "LifelineSessionStore"]
