"""Deterministic consequence summaries for SENTINEL impact explanations.

The summary does not add graph edges or infer service health. It projects only
objects already present in a proved blast radius into operator-friendly groups.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

_STORAGE_KINDS = {"disk", "vdev", "pool", "dataset"}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _text(value: Any) -> str:
    return str(value or "").strip()


def summarize_consequences(explanation: dict[str, Any] | None) -> dict[str, Any]:
    """Group existing proved impact without upgrading it into an outage claim."""

    source = explanation if isinstance(explanation, dict) else {}
    impacts = [
        deepcopy(item)
        for item in _list(source.get("known_impact"))
        if isinstance(item, dict)
        and _text(item.get("node_id"))
        and _text(item.get("kind"))
    ]
    impacts.sort(
        key=lambda item: (
            int(item.get("depth") or 0),
            _text(item.get("node_id")),
        )
    )

    storage = [item for item in impacts if _text(item.get("kind")) in _STORAGE_KINDS]
    applications = [
        item for item in impacts if _text(item.get("kind")) == "application"
    ]
    cargo = [item for item in impacts if _text(item.get("kind")) == "cargo"]
    backups = [
        item for item in impacts if _text(item.get("kind")) == "backup_evidence"
    ]

    running_apps = [
        item
        for item in applications
        if _text(item.get("state")).upper() == "RUNNING"
    ]

    return {
        "schema_version": 1,
        "read_only": True,
        "control_authority": False,
        "source_device": _text(source.get("source_device")) or None,
        "counts": {
            "proved_objects": len(impacts),
            "storage_objects": len(storage),
            "applications": len(applications),
            "running_applications": len(running_apps),
            "cargo": len(cargo),
            "backup_evidence": len(backups),
        },
        "storage": storage,
        "applications": applications,
        "cargo": cargo,
        "backup_evidence": backups,
        "language_guard": (
            "Presence in this summary means only that the object is reachable "
            "through proved SENTINEL graph edges. It does not prove an outage, "
            "service interruption, data loss, or user-visible impact."
        ),
    }


def attach_consequence_summaries(sentinel: dict[str, Any] | None) -> dict[str, Any] | None:
    """Attach consequence summaries to existing live explanations in place."""

    if not isinstance(sentinel, dict):
        return sentinel
    explanations = sentinel.get("explanations")
    if not isinstance(explanations, list):
        return sentinel

    for explanation in explanations:
        if isinstance(explanation, dict):
            explanation["consequences"] = summarize_consequences(explanation)
    return sentinel


__all__ = ["attach_consequence_summaries", "summarize_consequences"]
