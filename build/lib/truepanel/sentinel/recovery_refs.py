"""Evidence-bound Pathfinder references for SENTINEL explanations.

This module does not execute recovery or manufacture a procedure. It only links
an existing SENTINEL explanation to existing Pathfinder guidance when the
recovery contract proves that it refers to the same source device.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _text(value: Any) -> str:
    return str(value or "").strip()


def recovery_references_for_source(
    source_device: str,
    guidance_cards: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    """Return recovery references whose evidence exactly matches the source.

    A guidance title, severity, pool name, bay number, or similar contextual
    similarity is never enough to create a link. The decorated Pathfinder
    recovery contract must carry an exact device identity matching the SENTINEL
    source device. Conflicting runtime/recovery device identities fail closed.

    References deliberately omit mutable Pathfinder workflow state. The final
    HTTP composition layer may advance bookkeeping after the snapshot is built;
    SENTINEL only promises the stable procedure identity and current evidence
    gates that were already present in the guidance card.
    """

    source = _text(source_device)
    if not source:
        return []

    references: list[dict[str, Any]] = []
    for card in _list(guidance_cards):
        if not isinstance(card, dict):
            continue

        recovery = _dict(card.get("recovery"))
        evidence = _dict(recovery.get("evidence"))
        runtime_evidence = _dict(_dict(card.get("runtime")).get("evidence"))
        recovery_device = _text(evidence.get("device"))
        runtime_device = _text(runtime_evidence.get("device"))

        if recovery_device != source:
            continue
        if runtime_device and runtime_device != recovery_device:
            continue

        incident_id = _text(recovery.get("incident_id"))
        code = _text(recovery.get("code") or card.get("code"))
        if not incident_id or not code:
            continue

        reference = {
            "kind": "pathfinder_guidance",
            "source_device": source,
            "incident_id": incident_id,
            "code": code,
            "title": _text(card.get("title")) or code,
            "severity": _text(recovery.get("severity") or card.get("severity"))
            or "warning",
            "explanation": _text(recovery.get("explanation") or card.get("summary")),
            "verification": deepcopy(_dict(recovery.get("verification"))),
            "action_gate": deepcopy(_dict(recovery.get("action_gate"))),
            "authority": False,
        }
        references.append(reference)

    references.sort(
        key=lambda item: (
            str(item["code"]),
            str(item["incident_id"]),
        )
    )
    return references


def attach_recovery_references(
    sentinel: dict[str, Any] | None,
    guidance_cards: list[dict[str, Any]] | None,
) -> dict[str, Any] | None:
    """Attach read-only Pathfinder references to live SENTINEL explanations."""

    if not isinstance(sentinel, dict):
        return sentinel

    explanations = sentinel.get("explanations")
    if not isinstance(explanations, list):
        return sentinel

    for explanation in explanations:
        if not isinstance(explanation, dict):
            continue

        source = _text(explanation.get("source_device"))
        references = recovery_references_for_source(source, guidance_cards)
        recovery = _dict(explanation.get("recovery"))
        recovery = deepcopy(recovery)
        recovery["available"] = bool(references)
        recovery["authority"] = False
        recovery["references"] = references
        recovery["reason"] = (
            "Evidence-bound Pathfinder guidance is available for this exact "
            "SENTINEL source device. Reference availability does not grant "
            "repair or storage-mutation authority."
            if references
            else (
                "No existing Pathfinder recovery contract could be proven to "
                "refer to this exact SENTINEL source device."
            )
        )
        explanation["recovery"] = recovery

    return sentinel


__all__ = [
    "attach_recovery_references",
    "recovery_references_for_source",
]
