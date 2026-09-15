"""Fail-closed join between an AEGIS incident and SENTINEL proved impact.

This adapter deliberately does not perform causal inference.  AEGIS owns the
fault hypothesis; SENTINEL owns the dependency graph.  Consequence context is
attached only when both systems name one identical device and every displayed
path is already proved by SENTINEL.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from truepanel.guidance.storage_evidence import normalize_device

LANGUAGE_GUARD = (
    "Reachable through proved SENTINEL graph edges does not mean down. "
    "This context proves dependency reach only; it does not prove an outage, "
    "service interruption, data loss, or user-visible impact."
)


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _text(value: Any) -> str:
    return str(value or "").strip()


def _incident_devices(incident: dict[str, Any]) -> list[str]:
    devices = {
        device
        for item in _list(incident.get("supporting_signals"))
        if isinstance(item, dict) and item.get("source") == "verified_detector"
        if (device := _text(_dict(item.get("evidence")).get("device")))
    }
    return sorted(devices)


def _device(value: Any) -> str:
    normalized = normalize_device(value)
    return f"/dev/{normalized}" if normalized else ""


def _trusted_identity(value: Any) -> str:
    identity = _dict(value)
    stable_key = _text(identity.get("stable_key")).lower()
    mode = _text(identity.get("mode"))
    confidence = _text(identity.get("confidence"))
    prefix, separator, token = stable_key.partition(":")
    if (
        separator != ":"
        or prefix not in {"wwn", "serial", "zfs"}
        or len(token) != 24
        or any(character not in "0123456789abcdef" for character in token)
        or mode not in {"wwn", "serial_model", "zfs_member"}
        or confidence not in {"high", "very_high"}
        or identity.get("raw_serial_exposed") is not False
        or identity.get("raw_wwn_exposed") is not False
    ):
        return ""
    return stable_key


def _stable_identity_index(lifeline: Any) -> dict[str, Any]:
    """Index already-observed Lifeline identities without performing I/O."""

    root = _dict(lifeline)
    if root.get("read_only_hardware") is not True:
        return {"device_keys": {}, "cloned_keys": set()}
    sessions = [
        item
        for item in _list(root.get("sessions"))
        if isinstance(item, dict) and item.get("status") == "active"
    ]
    device_keys: dict[str, set[str]] = {}
    key_sessions: dict[str, set[str]] = {}
    for position, session in enumerate(sessions):
        stable_key = _trusted_identity(session.get("drive_identity"))
        if not stable_key:
            continue
        session_id = _text(session.get("id")) or f"position:{position}"
        key_sessions.setdefault(stable_key, set()).add(session_id)
        devices = {
            _device(session.get("current_device")),
            _device(_dict(session.get("original_fault")).get("device")),
            *(_device(value) for value in _list(session.get("device_history"))),
        }
        for current in devices - {""}:
            device_keys.setdefault(current, set()).add(stable_key)
    return {
        "device_keys": device_keys,
        "cloned_keys": {
            key for key, owners in key_sessions.items() if len(owners) != 1
        },
    }


def _identity_for_device(index: dict[str, Any], device: str) -> tuple[str, str]:
    keys = set(index["device_keys"].get(_device(device), set()))
    if len(keys) != 1:
        return "", f"observed {len(keys)} trusted Lifeline identities"
    stable_key = next(iter(keys))
    if stable_key in index["cloned_keys"]:
        return "", "stable identity is claimed by multiple active Lifeline sessions"
    return stable_key, ""


def _base(
    state: str,
    *,
    devices: list[str],
    reason: str,
    stable_identity: str | None = None,
    sentinel_device: str | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "state": state,
        "source": "SENTINEL_PROVED_GRAPH",
        "source_device": devices[0] if len(devices) == 1 else None,
        "sentinel_device": sentinel_device,
        "stable_identity": stable_identity,
        "identity_source": "LIFELINE_ACTIVE_SESSION",
        "incident_devices": devices,
        "reason": reason,
        "coverage_gap": None if state == "PROVED" else reason,
        "confidence_effect": "none",
        "diagnostic_confidence_unchanged": True,
        "read_only": True,
        "production_mutation": False,
        "control_authority": False,
        "language_guard": LANGUAGE_GUARD,
    }


def _safe_path(item: Any, *, source_device: str) -> dict[str, Any] | None:
    record = _dict(item)
    node_id = _text(record.get("node_id"))
    kind = _text(record.get("kind"))
    via = [_text(value) for value in _list(record.get("via")) if _text(value)]
    try:
        depth = int(record.get("depth"))
    except (TypeError, ValueError):
        return None
    if (
        not node_id
        or not kind
        or depth < 1
        or len(via) < 2
        or via[0] != f"disk:{source_device}"
        or via[-1] != node_id
    ):
        return None
    return {
        "node_id": node_id,
        "kind": kind,
        "label": _text(record.get("label")) or node_id,
        "state": _text(record.get("state")) or None,
        "depth": depth,
        "via": via,
    }


def correlate_consequences(
    incident: dict[str, Any] | None,
    sentinel: dict[str, Any] | None,
    lifeline: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return bounded proved dependency context without changing diagnosis."""

    active = _dict(incident)
    devices = _incident_devices(active)
    if not active:
        return _base("UNAVAILABLE", devices=[], reason="No active AEGIS incident.")
    if len(devices) != 1:
        reason = (
            "Impact topology requires exactly one detector-proved source device; "
            f"observed {len(devices)}."
        )
        return _base("HOLD", devices=devices, reason=reason)

    identity_index = _stable_identity_index(lifeline)
    stable_identity, identity_error = _identity_for_device(identity_index, devices[0])
    if not stable_identity:
        return _base(
            "HOLD",
            devices=devices,
            reason=(
                "Impact topology requires one trusted Lifeline identity for the "
                f"incident device; {identity_error}."
            ),
        )

    graph = _dict(sentinel)
    if (
        graph.get("read_only") is not True
        or graph.get("control_authority") is not False
    ):
        return _base(
            "HOLD",
            devices=devices,
            reason="SENTINEL safety-boundary evidence is missing or invalid.",
        )

    matches = []
    for item in _list(graph.get("explanations")):
        if not isinstance(item, dict):
            continue
        source_device = _device(item.get("source_device"))
        source_identity, _error = _identity_for_device(identity_index, source_device)
        if source_identity == stable_identity:
            matches.append(item)
    if len(matches) != 1:
        return _base(
            "HOLD",
            devices=devices,
            reason=(
                "Impact topology requires one SENTINEL source with the same trusted "
                "Lifeline identity; "
                f"observed {len(matches)}."
            ),
            stable_identity=stable_identity,
        )

    explanation = matches[0]
    sentinel_device = _device(explanation.get("source_device"))
    if (
        explanation.get("read_only") is not True
        or explanation.get("control_authority") is not False
    ):
        return _base(
            "HOLD",
            devices=devices,
            reason="Matched SENTINEL explanation lacks the read-only safety contract.",
            stable_identity=stable_identity,
            sentinel_device=sentinel_device,
        )

    raw_impacts = _list(explanation.get("known_impact"))
    impacts = [_safe_path(item, source_device=sentinel_device) for item in raw_impacts]
    if not raw_impacts or any(item is None for item in impacts):
        return _base(
            "HOLD",
            devices=devices,
            reason="Matched SENTINEL explanation contains no complete proved path set.",
            stable_identity=stable_identity,
            sentinel_device=sentinel_device,
        )
    proved = sorted(
        (item for item in impacts if item is not None),
        key=lambda item: (item["depth"], item["node_id"]),
    )

    counts = {
        "proved_objects": len(proved),
        "storage_objects": sum(
            item["kind"] in {"disk", "vdev", "pool", "dataset"} for item in proved
        ),
        "applications": sum(item["kind"] == "application" for item in proved),
        "running_applications": sum(
            item["kind"] == "application" and _text(item["state"]).upper() == "RUNNING"
            for item in proved
        ),
        "cargo": sum(item["kind"] == "cargo" for item in proved),
        "verified_backup_evidence": sum(
            item["kind"] == "backup_evidence"
            and _text(item["state"]).upper() == "VERIFIED"
            for item in proved
        ),
    }
    result = _base(
        "PROVED",
        devices=devices,
        reason=(
            "One trusted Lifeline identity joins the incident to proved SENTINEL "
            "paths, independent of the current Linux device address."
        ),
        stable_identity=stable_identity,
        sentinel_device=sentinel_device,
    )
    result.update(
        {
            "counts": counts,
            "proved_paths": deepcopy(proved),
            "unknowns": sorted(
                {
                    _text(item)
                    for item in _list(explanation.get("unknowns"))
                    if _text(item)
                }
            ),
            "recovery_reference_count": len(
                _list(_dict(explanation.get("recovery")).get("references"))
            ),
        }
    )
    return result


__all__ = ["LANGUAGE_GUARD", "correlate_consequences"]
