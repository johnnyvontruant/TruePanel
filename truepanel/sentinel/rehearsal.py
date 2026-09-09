"""Deterministic HoloDeck rehearsal contract for Project SENTINEL.

The rehearsal runner evaluates a fully synthetic snapshot against explicit
expectations. It performs no I/O and never grants control authority. The goal is
to make consequence claims testable before any operator-facing language is
added to Flight Director.
"""

from __future__ import annotations

from typing import Any

from .runtime import build_sentinel_snapshot


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _check(
    checks: list[dict[str, Any]],
    *,
    name: str,
    passed: bool,
    detail: str,
) -> None:
    checks.append({"name": name, "passed": bool(passed), "detail": detail})


def run_sentinel_rehearsal(document: dict[str, Any]) -> dict[str, Any]:
    """Run one deterministic SENTINEL rehearsal document.

    ``document`` contains a synthetic ``snapshot`` and an ``expect`` contract.
    The returned incident package deliberately distinguishes objects that are
    inside the proved blast radius from objects that are merely absent from it.
    Absence is *not* promoted to an "unaffected" claim.
    """

    scenario = _text(document.get("name")) or "unnamed-sentinel-rehearsal"
    snapshot = _dict(document.get("snapshot"))
    expect = _dict(document.get("expect"))
    sentinel = build_sentinel_snapshot(snapshot)

    reports = _list(sentinel.get("impact_reports"))
    source_device = _text(expect.get("source_device"))
    report = next(
        (
            item
            for item in reports
            if isinstance(item, dict)
            and _text(item.get("source_device")) == source_device
        ),
        None,
    )

    reachable = _list(_dict(report).get("reachable"))
    reachable_ids = {
        _text(item.get("node_id"))
        for item in reachable
        if isinstance(item, dict) and _text(item.get("node_id"))
    }
    all_nodes = {
        _text(item.get("id")): item
        for item in _list(_dict(sentinel.get("graph")).get("nodes"))
        if isinstance(item, dict) and _text(item.get("id"))
    }

    checks: list[dict[str, Any]] = []
    _check(
        checks,
        name="control-authority",
        passed=sentinel.get("control_authority") is False,
        detail="SENTINEL rehearsal must remain read-only with no control authority.",
    )
    _check(
        checks,
        name="source-impact-report",
        passed=report is not None,
        detail=f"Expected an actionable impact report for {source_device}.",
    )

    for node_id in sorted({_text(value) for value in _list(expect.get("reachable"))}):
        if not node_id:
            continue
        _check(
            checks,
            name=f"reachable:{node_id}",
            passed=node_id in reachable_ids,
            detail=f"{node_id} must be reachable from {source_device} by proved edges.",
        )

    for node_id in sorted(
        {_text(value) for value in _list(expect.get("not_in_proved_blast_radius"))}
    ):
        if not node_id:
            continue
        _check(
            checks,
            name=f"not-in-proved-blast-radius:{node_id}",
            passed=node_id not in reachable_ids,
            detail=(
                f"{node_id} must not be included in the proved blast radius. "
                "This does not claim the object is unaffected."
            ),
        )

    for node_id, state in sorted(_dict(expect.get("node_states")).items()):
        node = _dict(all_nodes.get(str(node_id)))
        actual = _text(node.get("state"))
        expected = _text(state)
        _check(
            checks,
            name=f"state:{node_id}",
            passed=actual == expected,
            detail=f"Expected {node_id} state {expected}; observed {actual or 'missing'}.",
        )

    unknowns = [
        _text(value)
        for value in _list(_dict(sentinel.get("assessment")).get("unknowns"))
    ]
    for fragment in [_text(value) for value in _list(expect.get("unknown_contains"))]:
        if not fragment:
            continue
        _check(
            checks,
            name=f"unknown:{fragment}",
            passed=any(fragment in unknown for unknown in unknowns),
            detail=f"Expected an explicit unknown containing: {fragment}",
        )

    affected = [
        {
            "node_id": item.get("node_id"),
            "kind": item.get("kind"),
            "label": item.get("label"),
            "state": item.get("state"),
            "depth": item.get("depth"),
            "via": item.get("via"),
        }
        for item in reachable
        if isinstance(item, dict)
    ]
    backup_evidence = [
        item
        for item in affected
        if item.get("kind") == "backup_evidence"
    ]

    passed = all(item["passed"] for item in checks)
    return {
        "schema_version": 1,
        "scenario": scenario,
        "passed": passed,
        "read_only": True,
        "control_authority": False,
        "checks": checks,
        "incident_package": {
            "source_device": source_device,
            "proved_blast_radius": affected,
            "backup_evidence": backup_evidence,
            "unknowns": unknowns,
            "language_guard": (
                "Objects absent from proved_blast_radius are not automatically "
                "classified as unaffected."
            ),
        },
        "sentinel": sentinel,
    }


__all__ = ["run_sentinel_rehearsal"]
