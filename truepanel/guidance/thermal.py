"""Evidence-bound thermal guidance adapter.

The adapter activates only when an upstream thermal domain explicitly marks an
over-temperature condition. It does not invent temperature limits from raw
sensor values.
"""

from __future__ import annotations

from typing import Any

from .catalog import guidance_payload


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def thermal_guidance_for_snapshot(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Return thermal guidance for an explicitly asserted thermal alarm."""

    thermal = _dict(payload.get("thermal"))
    active = (
        thermal.get("over_temperature") is True
        or thermal.get("alarm") is True
        or str(thermal.get("state", "")).strip().upper()
        in {"HOT", "HIGH", "CRITICAL", "OVER_TEMPERATURE"}
    )
    if not active:
        return []

    evidence = {
        "sensor_label": thermal.get("sensor_label") or thermal.get("sensor"),
        "current_temperature_c": thermal.get("current_temperature_c")
        if thermal.get("current_temperature_c") is not None
        else thermal.get("temperature_c"),
        "recent_peak_c": thermal.get("recent_peak_c"),
        "temperature_trend": thermal.get("temperature_trend"),
        "fan_rpm": thermal.get("fan_rpm"),
        "ambient_context": thermal.get("ambient_context"),
        "recovery_threshold_c": thermal.get("recovery_threshold_c"),
    }

    blocked_by = []
    if evidence["current_temperature_c"] is None:
        blocked_by.append("current_temperature_not_verified")
    if evidence["recovery_threshold_c"] is None:
        blocked_by.append("recovery_threshold_not_verified")

    card = guidance_payload("thermal.high_temperature")
    card["runtime"] = {
        "active": True,
        "phase": "diagnose",
        "evidence": evidence,
        "action_gate": {
            "safe_checks": True,
            "physical_service_ready": False,
            "destructive_actions_ready": False,
            "blocked_by": blocked_by,
        },
    }
    return [card]


__all__ = ["thermal_guidance_for_snapshot"]
