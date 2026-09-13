"""Fail-closed join between an AEGIS incident and SENTINEL proved impact.

This adapter deliberately does not perform causal inference.  AEGIS owns the
fault hypothesis; SENTINEL owns the dependency graph.  Consequence context is
attached only when both systems name one identical device and every displayed
path is already proved by SENTINEL.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

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


def _base(state: str, *, devices: list[str], reason: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "state": state,
        "source": "SENTINEL_PROVED_GRAPH",
        "source_device": devices[0] if len(devices) == 1 else None,
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

    graph = _dict(sentinel)
    if graph.get("read_only") is not True or graph.get("control_authority") is not False:
        return _base(
            "HOLD",
            devices=devices,
            reason="SENTINEL safety-boundary evidence is missing or invalid.",
        )

    matches = [
        item
        for item in _list(graph.get("explanations"))
        if isinstance(item, dict) and _text(item.get("source_device")) == devices[0]
    ]
    if len(matches) != 1:
        return _base(
            "HOLD",
            devices=devices,
            reason=(
                "Impact topology requires one exact SENTINEL source-device match; "
                f"observed {len(matches)}."
            ),
        )

    explanation = matches[0]
    if explanation.get("read_only") is not True or explanation.get("control_authority") is not False:
        return _base(
            "HOLD",
            devices=devices,
            reason="Matched SENTINEL explanation lacks the read-only safety contract.",
        )

    raw_impacts = _list(explanation.get("known_impact"))
    impacts = [_safe_path(item, source_device=devices[0]) for item in raw_impacts]
    if not raw_impacts or any(item is None for item in impacts):
        return _base(
            "HOLD",
            devices=devices,
            reason="Matched SENTINEL explanation contains no complete proved path set.",
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
        reason="One exact device identity joins the incident to proved SENTINEL paths.",
    )
    result.update(
        {
            "counts": counts,
            "proved_paths": deepcopy(proved),
            "unknowns": sorted(
                {_text(item) for item in _list(explanation.get("unknowns")) if _text(item)}
            ),
            "recovery_reference_count": len(
                _list(_dict(explanation.get("recovery")).get("references"))
            ),
        }
    )
    return result


__all__ = ["LANGUAGE_GUARD", "correlate_consequences"]
