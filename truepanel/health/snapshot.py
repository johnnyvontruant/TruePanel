"""Add health intelligence, operator guidance, and Lifeline repair sessions."""

from __future__ import annotations

from typing import Any

from truepanel.guidance import guidance_for_snapshot
from truepanel.lifeline import attach_repair_sessions

from .intelligence import HealthEvaluator


def augment_status_snapshot(
    payload: dict[str, Any],
    *,
    evaluator: HealthEvaluator | None = None,
) -> dict[str, Any]:
    """Return an additive health-aware copy of a status snapshot.

    Existing top-level values are preserved exactly. Health Intelligence,
    operator guidance, and Lifeline only consume those values and publish
    additive objects. Lifeline remains planning-only in this slice.
    """

    result = dict(payload)
    health_evaluator = evaluator or HealthEvaluator()

    result["health"] = health_evaluator.evaluate(
        fans=(
            payload.get("fans")
            if isinstance(payload.get("fans"), dict)
            else {}
        ),
        storage=(
            payload.get("storage")
            if isinstance(payload.get("storage"), dict)
            else {}
        ),
        network=(
            payload.get("network")
            if isinstance(payload.get("network"), list)
            else []
        ),
        lcd=(
            payload.get("lcd")
            if isinstance(payload.get("lcd"), dict)
            else {}
        ),
        services=(
            payload.get("services")
            if isinstance(payload.get("services"), dict)
            else {}
        ),
        capabilities=(
            payload.get("capabilities")
            if isinstance(payload.get("capabilities"), dict)
            else {}
        ),
    )

    guidance = guidance_for_snapshot(payload)
    lifeline_context = (
        payload.get("lifeline")
        if isinstance(payload.get("lifeline"), dict)
        else {}
    )
    result["operator_guidance"] = attach_repair_sessions(
        guidance,
        context=lifeline_context,
    )

    return result
