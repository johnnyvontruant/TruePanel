"""Add health intelligence to existing Mission Control snapshot payloads."""

from __future__ import annotations

from typing import Any

from .intelligence import HealthEvaluator


def augment_status_snapshot(
    payload: dict[str, Any],
    *,
    evaluator: HealthEvaluator | None = None,
) -> dict[str, Any]:
    """Return an additive health-aware copy of a status snapshot.

    Existing top-level values are preserved exactly. Health Intelligence only
    consumes those values and publishes a new ``health`` object.
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
        capabilities=(
            payload.get("capabilities")
            if isinstance(payload.get("capabilities"), dict)
            else {}
        ),
    )

    return result
