"""Deterministic Flight Director explanation contract for Project SENTINEL.

This module turns a SENTINEL incident package into bounded operator language.
It does not perform inference, I/O, recovery actions, or model calls.  Every
impact statement is derived from a proved graph path already present in the
incident package.
"""

from __future__ import annotations

from typing import Any


SCHEMA_VERSION = 1
LANGUAGE_GUARD = (
    "Objects absent from the proved blast radius are not automatically "
    "classified as unaffected."
)


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _text(value: Any) -> str:
    return str(value or "").strip()


def _safe_impact(item: Any) -> dict[str, Any] | None:
    record = _dict(item)
    node_id = _text(record.get("node_id"))
    kind = _text(record.get("kind"))
    if not node_id or not kind:
        return None

    via = [_text(value) for value in _list(record.get("via")) if _text(value)]
    if not via:
        return None

    try:
        depth = int(record.get("depth"))
    except (TypeError, ValueError):
        return None
    if depth < 1:
        return None

    return {
        "node_id": node_id,
        "kind": kind,
        "label": _text(record.get("label")) or node_id,
        "state": _text(record.get("state")) or None,
        "depth": depth,
        "via": via,
    }


def _impact_sort_key(item: dict[str, Any]) -> tuple[int, str]:
    return int(item["depth"]), str(item["node_id"])


def _fact_for_impact(source_device: str, item: dict[str, Any]) -> dict[str, Any]:
    label = item["label"]
    kind = item["kind"].replace("_", " ")
    state = item.get("state")
    statement = f"{label} is in the proved blast radius from {source_device}."
    if state:
        statement = (
            f"{label} is in the proved blast radius from {source_device}; "
            f"observed state is {state}."
        )
    return {
        "id": f"impact:{item['node_id']}",
        "status": "confirmed",
        "confidence": "high",
        "statement": statement,
        "provenance": {
            "type": "proved_graph_path",
            "path": list(item["via"]),
            "depth": item["depth"],
            "node_kind": kind,
        },
    }


def build_flight_director_explanation(
    incident_package: dict[str, Any] | None,
) -> dict[str, Any]:
    """Build a fail-closed, operator-facing explanation.

    The input is the structured ``incident_package`` emitted by SENTINEL's
    rehearsal/runtime boundary.  Malformed impact records are discarded rather
    than repaired.  If the source device or all usable impact paths are absent,
    the explanation degrades to ``HOLD`` and states what cannot be proved.
    """

    incident = _dict(incident_package)
    source_device = _text(incident.get("source_device"))
    impacts = [
        safe
        for item in _list(incident.get("proved_blast_radius"))
        if (safe := _safe_impact(item)) is not None
    ]
    impacts.sort(key=_impact_sort_key)

    unknowns = sorted(
        {
            _text(value)
            for value in _list(incident.get("unknowns"))
            if _text(value)
        }
    )

    output: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "read_only": True,
        "control_authority": False,
        "source_device": source_device or None,
        "state": "REVIEW",
        "headline": "SENTINEL storage impact review",
        "summary": "",
        "confirmed_facts": [],
        "known_impact": impacts,
        "protected_items": [],
        "unknowns": unknowns,
        "language_guard": LANGUAGE_GUARD,
        "recovery": {
            "available": False,
            "authority": False,
            "reason": (
                "Flight Director explanation v1 does not infer or execute a "
                "recovery procedure."
            ),
        },
    }

    if not source_device:
        output["state"] = "HOLD"
        output["headline"] = "SENTINEL cannot localize the incident source"
        output["summary"] = (
            "No source device is present in the incident package, so Flight "
            "Director cannot make a deterministic impact statement."
        )
        output["unknowns"] = sorted(
            set(
                [
                    *unknowns,
                    "Incident source is unavailable; downstream impact cannot be proved.",
                ]
            )
        )
        output["known_impact"] = []
        return output

    if not impacts:
        output["state"] = "HOLD"
        output["headline"] = f"SENTINEL cannot prove downstream impact for {source_device}"
        output["summary"] = (
            f"Actionable evidence may exist for {source_device}, but the incident "
            "package contains no valid proved downstream path."
        )
        output["unknowns"] = sorted(
            set(
                [
                    *unknowns,
                    (
                        f"Downstream impact for {source_device} is unknown because "
                        "no valid proved graph path is available."
                    ),
                ]
            )
        )
        return output

    output["confirmed_facts"] = [
        _fact_for_impact(source_device, item) for item in impacts
    ]

    protected: list[dict[str, Any]] = []
    for item in impacts:
        if item["kind"] != "backup_evidence":
            continue
        state = _text(item.get("state")).upper()
        if state != "VERIFIED":
            continue
        protected.append(
            {
                "node_id": item["node_id"],
                "label": item["label"],
                "state": "VERIFIED",
                "statement": (
                    f"Verified independent backup evidence is reachable for "
                    f"{item['label']}."
                ),
                "provenance": {
                    "type": "proved_graph_path",
                    "path": list(item["via"]),
                },
            }
        )
    output["protected_items"] = protected

    object_count = len(impacts)
    backup_count = len(protected)
    output["headline"] = f"SENTINEL localized downstream impact from {source_device}"
    output["summary"] = (
        f"SENTINEL can prove {object_count} downstream object"
        f"{'s' if object_count != 1 else ''} from {source_device}. "
        f"Verified independent backup evidence is present for {backup_count} "
        f"reachable object{'s' if backup_count != 1 else ''}. "
        "Objects not present in this proved blast radius are not classified as unaffected."
    )
    return output


__all__ = [
    "LANGUAGE_GUARD",
    "SCHEMA_VERSION",
    "build_flight_director_explanation",
]
