"""
Host-owned fan and thermal status publication.

The Host Agent is authoritative for fan-control state, thermal authority,
safety state, supervised sessions, and automatic-control leases.  This module
normalizes that state before publishing it through the existing atomic status
bridge.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from truepanel.hardware.bounded_automatic import (
    AUTOMATIC_LEASE_ALLOWED_PROFILES,
    AUTOMATIC_LEASE_SECONDS,
)


def publish_host_fan_status(
    *,
    fan_runtime: Any,
    thermal_authority: Any,
    status_bridge: Any,
    reason: str | None = None,
    monotonic: Callable[[], float] = time.monotonic,
) -> dict[str, Any]:
    """
    Publish one authoritative Host Agent fan-control status snapshot.

    Publication does not grant or change hardware authority.
    """

    payload = fan_runtime.status_payload()

    if reason is not None:
        payload["last_reason"] = reason

    recommendation = (
        thermal_authority.current_recommendation
    )

    payload["thermal_policy_mode"] = (
        thermal_authority.policy_mode
    )

    payload["thermal_operator_armed"] = bool(
        thermal_authority.operator_armed
    )

    payload["thermal_dry_run"] = bool(
        thermal_authority.coordinator.dry_run
    )

    control_result = (
        thermal_authority.last_result
    )

    payload["thermal_control_state"] = (
        control_result.state
        if control_result is not None
        else "awaiting_evaluation"
    )

    payload["thermal_control_reason"] = (
        control_result.reason
        if control_result is not None
        else (
            "Thermal control has not completed "
            "an evaluation cycle."
        )
    )

    payload["thermal_simulated_profile"] = (
        thermal_authority
        .coordinator
        .simulated_profile
        .value
    )

    payload[
        "thermal_control_cooldown_remaining"
    ] = (
        control_result.cooldown_remaining
        if control_result is not None
        else 0.0
    )

    session_remaining = 0.0

    deadline = (
        thermal_authority
        .supervised_session_deadline
    )

    if deadline is not None:
        session_remaining = max(
            0.0,
            deadline - monotonic(),
        )

    payload[
        "thermal_supervised_session_active"
    ] = bool(
        deadline is not None
        and session_remaining > 0
    )

    payload[
        "thermal_supervised_session_remaining"
    ] = session_remaining

    payload[
        "thermal_automatic_lease_active"
    ] = (
        thermal_authority
        .automatic_lease
        .active()
    )

    payload[
        "thermal_automatic_lease_remaining"
    ] = (
        thermal_authority
        .automatic_lease
        .remaining_seconds()
    )

    payload[
        "thermal_automatic_lease_seconds"
    ] = AUTOMATIC_LEASE_SECONDS

    payload[
        "thermal_automatic_allowed_profiles"
    ] = sorted(
        AUTOMATIC_LEASE_ALLOWED_PROFILES
    )

    payload["thermal_safety_fingerprint"] = (
        thermal_authority.current_fingerprint
    )

    payload[
        "thermal_commissioned_fingerprint"
    ] = (
        thermal_authority
        .commissioned_fingerprint
    )

    payload[
        "thermal_commissioned_fingerprint_match"
    ] = bool(
        thermal_authority.commissioned_fingerprint
        and (
            thermal_authority.current_fingerprint
            == thermal_authority
            .commissioned_fingerprint
        )
    )

    if recommendation is None:
        payload[
            "thermal_recommended_profile"
        ] = "automatic"

        payload[
            "thermal_hottest_temperature_c"
        ] = None

        payload[
            "thermal_recommendation_reason"
        ] = (
            "Thermal observer is awaiting telemetry."
        )

        payload[
            "thermal_recommendation_changed"
        ] = False

        payload[
            "thermal_telemetry_valid"
        ] = False

    else:
        payload[
            "thermal_recommended_profile"
        ] = (
            recommendation
            .recommended_profile
            .value
        )

        payload[
            "thermal_hottest_temperature_c"
        ] = (
            recommendation
            .hottest_temperature_c
        )

        payload[
            "thermal_recommendation_reason"
        ] = recommendation.reason

        payload[
            "thermal_recommendation_changed"
        ] = bool(
            recommendation.changed
        )

        payload[
            "thermal_telemetry_valid"
        ] = bool(
            recommendation.telemetry_valid
        )

    return status_bridge.publish(
        payload
    )


__all__ = [
    "publish_host_fan_status",
]
