"""Persistent, metadata-only Project Lifeline repair session ledger.

The ledger remembers the identity and progress of an operator repair across
changing telemetry and Mission Control refreshes. It writes only TruePanel
metadata and has no pool, disk, enclosure, or hardware-control authority.
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


def _integer(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _fault_key(evidence: dict[str, Any]) -> str | None:
    pool = _text(evidence.get("pool"))
    vdev = _text(evidence.get("vdev"))
    device = _text(evidence.get("device"))
    member_id = _text(evidence.get("member_id") or evidence.get("zfs_name"))
    identity = device or member_id
    if not pool or not vdev or not identity:
        return None
    return f"drive:{pool}:{vdev}:{identity}"


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
        except (OSError, TypeError, ValueError):
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
            sessions.sort(
                key=lambda item: (
                    float(item.get("created_at", 0.0)),
                    str(item.get("id", "")),
                )
            )
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

    def set_historical_physical_identity(
        self,
        session_id: str,
        *,
        member_id: str,
        bay: int,
        serial_last4: str,
        source: str,
    ) -> dict[str, Any]:
        """Persist verified historical member-to-bay provenance.

        This is metadata-only commissioning state. It cannot be used to
        override a currently present Linux device, and the asserted member ID
        must exactly match the immutable original fault identity.
        """

        member_id = _text(member_id)
        serial_last4 = _text(serial_last4)
        source = _text(source)
        try:
            bay = int(bay)
        except (TypeError, ValueError) as error:
            raise ValueError("historical physical bay must be an integer") from error

        if not member_id:
            raise ValueError("historical member identity is required")
        if bay <= 0:
            raise ValueError("historical physical bay must be positive")
        if not serial_last4:
            raise ValueError("historical serial identity is required")
        if not source:
            raise ValueError("historical identity provenance source is required")

        with self._lock:
            session = self._state["sessions"].get(str(session_id))
            if not isinstance(session, dict):
                raise KeyError("unknown Lifeline session")

            original = _dict(session.get("original_fault"))
            original_member = _text(original.get("member_id"))
            if member_id != original_member:
                raise ValueError("historical identity does not match original fault member")
            if _text(original.get("device")):
                raise ValueError(
                    "historical identity cannot override a current Linux device identity"
                )

            context = session.setdefault("context", {})
            context["physical_identity"] = {
                "verified": True,
                "kind": "historical_verified",
                "member_id": member_id,
                "bay": bay,
                "serial_last4": serial_last4,
                "source": source,
            }
            session["updated_at"] = float(self.clock())
            self._save()
            return deepcopy(session)

    def set_historical_media_properties(
        self,
        session_id: str,
        *,
        member_id: str,
        serial_last4: str,
        capacity_bytes: int,
        source: str,
        model: str | None = None,
    ) -> dict[str, Any]:
        """Persist verified historical capacity/model evidence for a removed member.

        Historical media properties are accepted only after the same member
        and serial suffix have already been commissioned as physical identity.
        They never override a current Linux device or live capacity reading.
        """

        member_id = _text(member_id)
        serial_last4 = _text(serial_last4)
        source = _text(source)
        model = _text(model) or None
        try:
            capacity_bytes = int(capacity_bytes)
        except (TypeError, ValueError) as error:
            raise ValueError("historical media capacity must be an integer") from error

        if not member_id:
            raise ValueError("historical member identity is required")
        if not serial_last4:
            raise ValueError("historical serial identity is required")
        if capacity_bytes <= 0:
            raise ValueError("historical media capacity must be positive")
        if not source:
            raise ValueError("historical media provenance source is required")

        with self._lock:
            session = self._state["sessions"].get(str(session_id))
            if not isinstance(session, dict):
                raise KeyError("unknown Lifeline session")

            original = _dict(session.get("original_fault"))
            if member_id != _text(original.get("member_id")):
                raise ValueError("historical media does not match original fault member")
            if _text(original.get("device")):
                raise ValueError(
                    "historical media cannot override a current Linux device identity"
                )

            context = session.setdefault("context", {})
            physical_identity = _dict(context.get("physical_identity"))
            if not (
                physical_identity.get("verified") is True
                and physical_identity.get("kind") == "historical_verified"
                and _text(physical_identity.get("member_id")) == member_id
                and _text(physical_identity.get("serial_last4")) == serial_last4
            ):
                raise ValueError(
                    "historical media requires verified matching physical identity"
                )

            context["historical_media"] = {
                "verified": True,
                "kind": "historical_verified",
                "member_id": member_id,
                "serial_last4": serial_last4,
                "capacity_bytes": capacity_bytes,
                "model": model,
                "source": source,
            }
            session["updated_at"] = float(self.clock())
            self._save()
            return deepcopy(session)

    def set_replacement_candidates(
        self,
        session_id: str,
        candidates: list[dict[str, Any]],
    ) -> dict[str, Any]:
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

    def _active_for_fault(self, key: str) -> dict[str, Any] | None:
        for session in self._state["sessions"].values():
            if not isinstance(session, dict):
                continue
            if session.get("status") != "active":
                continue
            if session.get("fault_key") == key:
                return session
        return None

    def _next_attempt(self, key: str) -> int:
        attempts = [
            int(item.get("attempt", 0) or 0)
            for item in self._state["sessions"].values()
            if isinstance(item, dict) and item.get("fault_key") == key
        ]
        return max(attempts, default=0) + 1

    def _new_session(self, key: str, evidence: dict[str, Any]) -> dict[str, Any]:
        now = float(self.clock())
        attempt = self._next_attempt(key)
        session_id = f"{key}:attempt-{attempt}"
        original = {
            "pool": evidence.get("pool"),
            "vdev": evidence.get("vdev"),
            "vdev_topology": evidence.get("vdev_topology"),
            "remaining_redundancy": evidence.get("remaining_redundancy"),
            "member_id": evidence.get("member_id") or evidence.get("zfs_name"),
            "historical_path": evidence.get("historical_path"),
            "device": evidence.get("device"),
            "bay": evidence.get("bay"),
            "model": evidence.get("model"),
            "serial_last4": evidence.get("serial_last4"),
            "capacity_bytes": evidence.get("capacity_bytes"),
        }
        session = {
            "id": session_id,
            "fault_key": key,
            "attempt": attempt,
            "kind": "drive_replacement",
            "status": "active",
            "created_at": now,
            "updated_at": now,
            "original_fault": original,
            "context": {
                "service_procedure_verified": False,
                "service_profile": None,
                "service_source": None,
                "physical_identity": None,
                "historical_media": None,
                "acknowledgements": {
                    "backup_state": False,
                },
                "replacement_candidates": [],
            },
            "healthy_observations": 0,
            "last_session": None,
        }
        self._state["sessions"][session_id] = session
        return session

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

        repair_evidence = dict(evidence)
        bay_identity_verified: bool | None = None
        physical_identity = _dict(context.get("physical_identity"))
        current_member = _text(
            repair_evidence.get("member_id") or repair_evidence.get("zfs_name")
        )
        historical_member = _text(physical_identity.get("member_id"))
        if (
            physical_identity.get("verified") is True
            and physical_identity.get("kind") == "historical_verified"
            and current_member
            and historical_member == current_member
            and not _text(repair_evidence.get("device"))
        ):
            try:
                historical_bay = int(physical_identity.get("bay"))
            except (TypeError, ValueError):
                historical_bay = 0
            serial_last4 = _text(physical_identity.get("serial_last4"))
            source = _text(physical_identity.get("source"))
            if historical_bay > 0 and serial_last4 and source:
                repair_evidence["bay"] = historical_bay
                repair_evidence["physical_identity_source"] = "historical_verified"
                repair_evidence["physical_identity_serial_last4"] = serial_last4
                bay_identity_verified = True

        historical_media = _dict(context.get("historical_media"))
        if (
            historical_media.get("verified") is True
            and historical_media.get("kind") == "historical_verified"
            and current_member
            and _text(historical_media.get("member_id")) == current_member
            and _text(historical_media.get("serial_last4"))
            == _text(physical_identity.get("serial_last4"))
            and not _text(repair_evidence.get("device"))
        ):
            historical_capacity = _integer(
                historical_media.get("capacity_bytes")
            )
            historical_source = _text(historical_media.get("source"))
            if historical_capacity is not None and historical_capacity > 0 and historical_source:
                if _integer(repair_evidence.get("capacity_bytes")) is None:
                    repair_evidence["capacity_bytes"] = historical_capacity
                    repair_evidence["capacity_source"] = "historical_verified"
                historical_model = _text(historical_media.get("model"))
                if historical_model and not _text(repair_evidence.get("model")):
                    repair_evidence["model"] = historical_model

        repair = evaluate_drive_repair(
            repair_evidence,
            service_procedure_verified=bool(
                context.get("service_procedure_verified", False)
            ),
            backup_acknowledged=bool(
                acknowledgements.get("backup_state", False)
            ),
            bay_identity_verified=bay_identity_verified,
            replacement_candidate=candidate,
            replacement_operation_confirmed=False,
        )
        return repair.to_payload()

    def observe(self, payload: dict[str, Any]) -> dict[str, Any]:
        result = deepcopy(payload)
        guidance = _list(result.get("operator_guidance"))
        now = float(self.clock())
        changed = False
        seen_faults: set[str] = set()

        with self._lock:
            sessions = self._state["sessions"]

            for item in guidance:
                if not isinstance(item, dict) or item.get("code") != "storage.disk_faulted":
                    continue
                runtime = _dict(item.get("runtime"))
                evidence = _dict(runtime.get("evidence"))
                key = _fault_key(evidence)
                if key is None:
                    continue
                seen_faults.add(key)
                ledger = self._active_for_fault(key)
                if ledger is None:
                    ledger = self._new_session(key, evidence)
                    changed = True

                if ledger.get("healthy_observations") != 0:
                    ledger["healthy_observations"] = 0
                    changed = True
                ledger["updated_at"] = now
                repair = self._evaluate(ledger, evidence)
                if ledger.get("last_session") != repair:
                    ledger["last_session"] = repair
                    changed = True
                item["repair_session"] = deepcopy(repair)

            for ledger in list(sessions.values()):
                if not isinstance(ledger, dict) or ledger.get("status") != "active":
                    continue
                if ledger.get("fault_key") in seen_faults:
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
