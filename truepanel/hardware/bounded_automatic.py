"""
Bounded automatic thermal-control lease primitives.

This module contains no hardware writes. It validates the commissioned
configuration fingerprint, constrains the automatic profile envelope, and
tracks an ephemeral runtime lease.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from typing import Any, Callable, Mapping

AUTOMATIC_LEASE_SECONDS = 600.0
AUTOMATIC_LEASE_ALLOWED_PROFILES = frozenset(
    {
        "balanced",
        "cooling_boost",
    }
)

_SAFETY_FINGERPRINT_PATHS = (
    ("hardware", "fan_control", "enabled"),
    ("hardware", "fan_control", "command_timeout"),
    ("hardware", "fan_control", "afterburners_timeout"),
    ("hardware", "fan_control", "safety_recovery_cycles"),
    ("hardware", "fan_control", "controlled_channels"),
    ("hardware", "fan_control", "profiles"),
    ("hardware", "thermal_policy", "mode"),
    ("hardware", "thermal_policy", "command_cooldown_seconds"),
    ("hardware", "thermal_policy", "balanced_temperature_c"),
    ("hardware", "thermal_policy", "cooling_boost_temperature_c"),
    ("hardware", "thermal_policy", "afterburners_temperature_c"),
    ("hardware", "thermal_policy", "hysteresis_c"),
    ("hardware", "thermal_policy", "minimum_dwell_seconds"),
)


def _nested_value(
    config: Mapping[str, Any],
    path: tuple[str, ...],
) -> Any:
    value: Any = config

    for key in path:
        if not isinstance(value, Mapping):
            return None
        value = value.get(key)

    return value


def thermal_safety_contract(
    config: Mapping[str, Any],
) -> dict[str, Any]:
    """Return only safety-critical fan and thermal configuration."""

    contract: dict[str, Any] = {}

    for path in _SAFETY_FINGERPRINT_PATHS:
        destination = contract

        for key in path[:-1]:
            destination = destination.setdefault(key, {})

        destination[path[-1]] = _nested_value(
            config,
            path,
        )

    return contract


def thermal_safety_fingerprint(
    config: Mapping[str, Any],
) -> str:
    """Create a stable SHA-256 fingerprint for the safety contract."""

    canonical = json.dumps(
        thermal_safety_contract(config),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")

    return hashlib.sha256(canonical).hexdigest()


@dataclass(frozen=True)
class AutomaticLeaseDecision:
    accepted: bool
    status: str
    message: str
    blocking_reasons: tuple[str, ...] = ()


class BoundedAutomaticLease:
    """Track an ephemeral, bounded automatic-control authorization."""

    def __init__(
        self,
        *,
        commissioned_fingerprint: str,
        duration_seconds: float = AUTOMATIC_LEASE_SECONDS,
        clock: Callable[[], float] | None = None,
    ):
        duration = float(duration_seconds)

        if duration <= 0:
            raise ValueError(
                "Automatic lease duration must be positive."
            )

        fingerprint = str(
            commissioned_fingerprint
            or ""
        ).strip().lower()

        if fingerprint and len(fingerprint) != 64:
            raise ValueError(
                "Commissioned fingerprint must be a SHA-256 digest."
            )

        self.commissioned_fingerprint = fingerprint
        self.duration_seconds = duration
        self.clock = clock or time.monotonic
        self.deadline: float | None = None

    def active(self) -> bool:
        return (
            self.deadline is not None
            and float(self.clock()) < self.deadline
        )

    def remaining_seconds(self) -> float:
        if self.deadline is None:
            return 0.0

        return max(
            0.0,
            self.deadline - float(self.clock()),
        )

    def cancel(self) -> bool:
        was_active = self.deadline is not None
        self.deadline = None
        return was_active

    @staticmethod
    def profile_allowed(profile: Any) -> bool:
        return (
            str(profile).strip().lower()
            in AUTOMATIC_LEASE_ALLOWED_PROFILES
        )

    def start(
        self,
        *,
        current_fingerprint: str,
        active_profile: Any,
        recommended_profile: Any,
        telemetry_valid: bool,
        telemetry_fresh: bool,
        connected: bool,
        safety_hold: bool,
        recovery_pending: bool,
    ) -> AutomaticLeaseDecision:
        blocking: list[str] = []

        if (
            str(current_fingerprint).strip().lower()
            != self.commissioned_fingerprint
        ):
            blocking.append(
                "The active fan and thermal configuration does not "
                "match the commissioned safety fingerprint."
            )

        if str(active_profile).strip().lower() != "automatic":
            blocking.append(
                "Bounded automatic control must begin from "
                "motherboard automatic mode."
            )

        if not self.profile_allowed(recommended_profile):
            blocking.append(
                "The current recommendation is outside the bounded "
                "automatic profile envelope."
            )

        if not telemetry_valid:
            blocking.append(
                "Thermal recommendation telemetry is invalid."
            )

        if not telemetry_fresh:
            blocking.append(
                "Thermal telemetry is stale."
            )

        if not connected:
            blocking.append(
                "Fan-control runtime is disconnected."
            )

        if safety_hold:
            blocking.append(
                "Fan-control safety hold is active."
            )

        if recovery_pending:
            blocking.append(
                "Fan-control safety recovery is pending."
            )

        if blocking:
            return AutomaticLeaseDecision(
                accepted=False,
                status="readiness_blocked",
                message=blocking[0],
                blocking_reasons=tuple(blocking),
            )

        self.deadline = (
            float(self.clock())
            + self.duration_seconds
        )

        return AutomaticLeaseDecision(
            accepted=True,
            status="automatic_lease",
            message=(
                "Bounded automatic thermal control engaged for "
                f"{self.duration_seconds:.0f} seconds."
            ),
        )


__all__ = [
    "AUTOMATIC_LEASE_ALLOWED_PROFILES",
    "AUTOMATIC_LEASE_SECONDS",
    "AutomaticLeaseDecision",
    "BoundedAutomaticLease",
    "thermal_safety_contract",
    "thermal_safety_fingerprint",
]
