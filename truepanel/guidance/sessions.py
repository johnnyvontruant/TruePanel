"""Persistent workflow memory for Project Pathfinder guided recovery.

The live guidance contract remains authoritative for telemetry, verification,
and every hardware/storage safety gate. This store persists only workflow
progress and a bounded recovery timeline so an operator does not lose context
when Mission Control refreshes or restarts.
"""

from __future__ import annotations

import json
import os
import tempfile
import time
from copy import deepcopy
from pathlib import Path
from typing import Any, Callable

from .recovery import transition_recovery

RECOVERY_SESSION_SCHEMA_VERSION = 1
DEFAULT_RECOVERY_SESSION_PATH = Path(
    "/var/lib/truepanel/pathfinder/recovery-sessions.json"
)

_STATE_ORDER = {
    "detected": 0,
    "reviewing": 1,
    "diagnosing": 2,
    "repairing": 3,
    "verifying": 4,
    "resolved": 5,
}

_FORWARD_PATH = {
    "detected": "reviewing",
    "reviewing": "diagnosing",
    "diagnosing": "repairing",
    "repairing": "verifying",
    "verifying": "resolved",
}

_SUBSYSTEM_FOR_CODE = {
    "cooling.fan_stall": "cooling",
    "thermal.high_temperature": "thermal",
    "storage.smart_warning": "storage",
    "storage.pool_degraded": "storage",
    "storage.disk_faulted": "storage",
    "network.link_down": "network",
    "front_panel.lcd_unavailable": "front_panel",
}


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _text(value: Any) -> str:
    return str(value or "").strip()


def _allowed_for(state: str) -> list[str]:
    return {
        "detected": ["reviewing", "diagnosing"],
        "reviewing": ["diagnosing"],
        "diagnosing": ["repairing", "verifying"],
        "repairing": ["verifying"],
        "verifying": ["resolved", "diagnosing", "repairing"],
        "resolved": [],
    }.get(state, [])


def _workflow_record(contract: dict[str, Any], *, seen_at: float) -> dict[str, Any]:
    state = _text(contract.get("state")).lower() or "reviewing"
    try:
        clear_observations = max(0, int(contract.get("clear_observations") or 0))
    except (TypeError, ValueError):
        clear_observations = 0
    return {
        "incident_id": _text(contract.get("incident_id")),
        "code": _text(contract.get("code")),
        "state": state,
        "allowed_transitions": _allowed_for(state),
        "timeline": [
            deepcopy(item)
            for item in _list(contract.get("timeline"))[-64:]
            if isinstance(item, dict)
        ],
        "clear_observations": clear_observations,
        "last_seen": float(seen_at),
    }


def _merge_live_contract(
    live: dict[str, Any],
    workflow: dict[str, Any],
) -> dict[str, Any]:
    """Overlay workflow progress without overriding live evidence/safety."""

    merged = deepcopy(live)
    state = _text(workflow.get("state")).lower() or _text(live.get("state")).lower()
    merged["state"] = state
    merged["allowed_transitions"] = _allowed_for(state)
    merged["timeline"] = [
        deepcopy(item)
        for item in _list(workflow.get("timeline"))[-64:]
        if isinstance(item, dict)
    ]
    return merged


def _subsystem_state(payload: dict[str, Any], code: str) -> tuple[str, str]:
    subsystem = _SUBSYSTEM_FOR_CODE.get(code, "")
    if not subsystem:
        return "", ""
    health = _dict(payload.get("health"))
    subsystems = _dict(health.get("subsystems"))
    result = _dict(subsystems.get(subsystem))
    return subsystem, _text(result.get("state")).upper()


class RecoverySessionStore:
    """Persist Pathfinder workflow state without persisting telemetry evidence."""

    def __init__(
        self,
        path: str | Path | None = DEFAULT_RECOVERY_SESSION_PATH,
        *,
        clock: Callable[[], float] = time.time,
        maximum_sessions: int = 256,
        clear_observations_required: int = 2,
    ) -> None:
        self.path = Path(path) if path is not None else None
        self.clock = clock
        self.maximum_sessions = max(8, int(maximum_sessions))
        self.clear_observations_required = max(2, int(clear_observations_required))
        self._sessions: dict[str, dict[str, Any]] = {}
        self._load()

    def observe(self, cards: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Attach durable workflow progress to freshly evaluated guidance."""

        decorated, changed = self._observe_cards(cards)
        if self._prune():
            changed = True
        if changed:
            self._persist()
        return decorated

    def observe_snapshot(
        self,
        cards: list[dict[str, Any]],
        payload: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Reconcile active cards and safely verify faults that disappeared.

        Guidance cards normally disappear when their triggering condition
        clears. Pathfinder therefore uses the already-normalized subsystem
        health contract as a second, privacy-safe verification source. An
        absent incident is closed only after repeated NOMINAL observations of
        its mapped subsystem. UNKNOWN, missing, or non-nominal health can never
        manufacture a successful repair.
        """

        decorated, changed = self._observe_cards(cards)
        active_ids = {
            _text(_dict(card.get("recovery")).get("incident_id"))
            for card in decorated
            if isinstance(card, dict)
        }
        now = float(self.clock())

        for incident_id, stored in list(self._sessions.items()):
            if incident_id in active_ids or not isinstance(stored, dict):
                continue
            state = _text(stored.get("state")).lower()
            if state == "resolved":
                continue

            code = _text(stored.get("code"))
            subsystem, health_state = _subsystem_state(payload, code)
            current = deepcopy(stored)
            current["last_seen"] = now

            if health_state != "NOMINAL":
                if int(current.get("clear_observations") or 0) != 0:
                    current["clear_observations"] = 0
                    self._sessions[incident_id] = _workflow_record(
                        current,
                        seen_at=now,
                    )
                    changed = True
                continue

            clear_count = int(current.get("clear_observations") or 0) + 1
            current["clear_observations"] = clear_count
            changed = True

            if clear_count >= self.clear_observations_required:
                while _text(current.get("state")).lower() != "verifying":
                    current_state = _text(current.get("state")).lower()
                    if current_state in {"resolved", "verifying"}:
                        break
                    step = _FORWARD_PATH.get(current_state)
                    if not step:
                        break
                    current = transition_recovery(
                        current,
                        step,
                        "fault_condition_cleared",
                        automated=True,
                        evidence={"subsystem": subsystem},
                    )
                    current["clear_observations"] = clear_count

                if _text(current.get("state")).lower() == "verifying":
                    current = transition_recovery(
                        current,
                        "resolved",
                        "subsystem_health_verified",
                        automated=True,
                        evidence={
                            "subsystem": subsystem,
                            "state": "NOMINAL",
                            "observations": clear_count,
                        },
                    )
                    current["clear_observations"] = clear_count

            self._sessions[incident_id] = _workflow_record(
                current,
                seen_at=now,
            )

        if self._prune():
            changed = True
        if changed:
            self._persist()
        return decorated

    def _observe_cards(
        self,
        cards: list[dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], bool]:
        now = float(self.clock())
        decorated: list[dict[str, Any]] = []
        changed = False

        for card in cards:
            if not isinstance(card, dict):
                continue
            item = deepcopy(card)
            live = _dict(item.get("recovery"))
            incident_id = _text(live.get("incident_id"))
            if not incident_id:
                decorated.append(item)
                continue

            stored = self._sessions.get(incident_id)
            if not isinstance(stored, dict):
                stored = _workflow_record(live, seen_at=now)
                changed = True
            else:
                stored = deepcopy(stored)

            stored["clear_observations"] = 0
            stored = self._reconcile(stored, live, seen_at=now)
            if stored != self._sessions.get(incident_id):
                changed = True
            self._sessions[incident_id] = stored
            item["recovery"] = _merge_live_contract(live, stored)
            decorated.append(item)

        return decorated, changed

    def transition(
        self,
        incident_id: str,
        next_state: str,
        event: str,
        *,
        automated: bool = False,
        evidence: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Persist one legal workflow transition.

        This records operator workflow only. It cannot alter a live guidance
        action gate, execute a repair, or manufacture verification evidence.
        """

        key = _text(incident_id)
        if not key or key not in self._sessions:
            raise KeyError(f"unknown recovery incident: {key or '<empty>'}")

        current = deepcopy(self._sessions[key])
        updated = transition_recovery(
            current,
            next_state,
            event,
            automated=automated,
            evidence=evidence,
        )
        updated["last_seen"] = float(self.clock())
        self._sessions[key] = _workflow_record(
            updated,
            seen_at=updated["last_seen"],
        )
        self._persist()
        return deepcopy(self._sessions[key])

    def snapshot(self) -> dict[str, Any]:
        """Return privacy-minimal workflow metadata for diagnostics."""

        sessions = sorted(
            (deepcopy(value) for value in self._sessions.values()),
            key=lambda item: float(item.get("last_seen") or 0.0),
            reverse=True,
        )
        return {
            "schema_version": RECOVERY_SESSION_SCHEMA_VERSION,
            "metadata_only": True,
            "count": len(sessions),
            "sessions": sessions,
        }

    def _reconcile(
        self,
        stored: dict[str, Any],
        live: dict[str, Any],
        *,
        seen_at: float,
    ) -> dict[str, Any]:
        stored_state = _text(stored.get("state")).lower() or "reviewing"
        live_state = _text(live.get("state")).lower() or "reviewing"
        verification = _dict(live.get("verification"))

        if (
            stored_state == "resolved"
            and live_state != "resolved"
            and _text(verification.get("status")).lower() != "passed"
        ):
            reopened = _workflow_record(live, seen_at=seen_at)
            reopened["state"] = live_state
            reopened["allowed_transitions"] = _allowed_for(live_state)
            reopened["timeline"] = [
                *[
                    deepcopy(item)
                    for item in _list(stored.get("timeline"))[-63:]
                    if isinstance(item, dict)
                ],
                {
                    "state": live_state,
                    "event": "incident_reappeared",
                    "automated": True,
                },
            ]
            return reopened

        current = deepcopy(stored)
        current["last_seen"] = float(seen_at)

        target_rank = _STATE_ORDER.get(live_state, 1)
        current_rank = _STATE_ORDER.get(stored_state, 1)
        while current_rank < target_rank:
            current_state = _text(current.get("state")).lower()
            # Entering RESOLVED is intentionally not a generic phase advance.
            # Preserve the verified evidence and dedicated timeline event that
            # proves why Pathfinder closed the incident.
            if current_state == "verifying":
                break
            step = _FORWARD_PATH.get(current_state)
            if not step:
                break
            current = transition_recovery(
                current,
                step,
                "telemetry_phase_advanced",
                automated=True,
            )
            current_rank = _STATE_ORDER.get(step, current_rank)

        if (
            _text(current.get("state")).lower() == "verifying"
            and _text(verification.get("status")).lower() == "passed"
        ):
            current = transition_recovery(
                current,
                "resolved",
                "verification_passed",
                automated=True,
                evidence={
                    "strategy": _text(verification.get("strategy")),
                },
            )

        return _workflow_record(current, seen_at=seen_at)

    def _load(self) -> None:
        if self.path is None:
            return
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            return
        if not isinstance(payload, dict):
            return
        records = payload.get("sessions")
        if not isinstance(records, list):
            return
        for record in records:
            if not isinstance(record, dict):
                continue
            incident_id = _text(record.get("incident_id"))
            state = _text(record.get("state")).lower()
            if not incident_id or state not in _STATE_ORDER:
                continue
            try:
                clear_observations = max(
                    0,
                    int(record.get("clear_observations") or 0),
                )
            except (TypeError, ValueError):
                clear_observations = 0
            self._sessions[incident_id] = {
                "incident_id": incident_id,
                "code": _text(record.get("code")),
                "state": state,
                "allowed_transitions": _allowed_for(state),
                "timeline": [
                    deepcopy(item)
                    for item in _list(record.get("timeline"))[-64:]
                    if isinstance(item, dict)
                ],
                "clear_observations": clear_observations,
                "last_seen": float(record.get("last_seen") or 0.0),
            }

    def _persist(self) -> None:
        if self.path is None:
            return
        try:
            parent = self.path.parent
            parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            try:
                os.chmod(parent, 0o700)
            except OSError:
                pass

            payload = self.snapshot()
            data = json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n"
            fd, temporary = tempfile.mkstemp(
                prefix=f".{self.path.name}.",
                dir=str(parent),
                text=True,
            )
            try:
                os.fchmod(fd, 0o600)
                with os.fdopen(fd, "w", encoding="utf-8") as handle:
                    handle.write(data)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temporary, self.path)
                os.chmod(self.path, 0o600)
            finally:
                try:
                    os.unlink(temporary)
                except FileNotFoundError:
                    pass
        except OSError:
            # Workflow memory is a convenience layer. If persistence is
            # unavailable, Mission Control must keep running from fresh live
            # telemetry and the original safety gates.
            return

    def _prune(self) -> bool:
        if len(self._sessions) <= self.maximum_sessions:
            return False
        ordered = sorted(
            self._sessions.items(),
            key=lambda item: float(item[1].get("last_seen") or 0.0),
            reverse=True,
        )
        self._sessions = dict(ordered[: self.maximum_sessions])
        return True


__all__ = [
    "DEFAULT_RECOVERY_SESSION_PATH",
    "RECOVERY_SESSION_SCHEMA_VERSION",
    "RecoverySessionStore",
]
