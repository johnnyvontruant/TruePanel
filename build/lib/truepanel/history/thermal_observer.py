"""
Observe-only thermal recommendation history.

This module records meaningful thermal-policy transitions in a bounded JSONL
file. It contains no fan command, executor, PWM, or hardware-write surface.
"""

from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any, Callable, Mapping


DEFAULT_THERMAL_OBSERVER_HISTORY_PATH = Path(
    "/var/lib/truepanel/history/"
    "thermal-observer.jsonl"
)

_ALLOWED_PROFILES = {
    "automatic",
    "quiet",
    "balanced",
    "cooling_boost",
    "afterburners",
}


def _safe_profile(
    value: Any,
) -> str:
    profile = str(
        value
        or "automatic"
    ).strip().lower()

    if profile not in _ALLOWED_PROFILES:
        return "automatic"

    return profile


def event_from_recommendation(
    recommendation,
    *,
    active_profile: str = "automatic",
    control_authority: str = "automatic",
    policy_mode: str = "observe_only",
    previous_recommended_profile: str = "automatic",
    timestamp: float | None = None,
) -> dict[str, Any]:
    """Build a normalized thermal-observer history event."""

    recommended = getattr(
        recommendation,
        "recommended_profile",
        "automatic",
    )

    recommended = getattr(
        recommended,
        "value",
        recommended,
    )

    hottest = getattr(
        recommendation,
        "hottest_temperature_c",
        None,
    )

    recommended_profile = _safe_profile(
        recommended
    )
    previous_profile = _safe_profile(
        previous_recommended_profile
    )
    active_profile = _safe_profile(
        active_profile
    )

    ranks = {
        "automatic": 0,
        "quiet": 1,
        "balanced": 2,
        "cooling_boost": 3,
        "afterburners": 4,
    }

    if recommended_profile == previous_profile:
        transition_direction = "steady"
    elif (
        ranks[recommended_profile]
        > ranks[previous_profile]
    ):
        transition_direction = "upshift"
    else:
        transition_direction = "downshift"

    telemetry_valid = bool(
        getattr(
            recommendation,
            "telemetry_valid",
            False,
        )
    )

    if not telemetry_valid:
        profile_alignment = "telemetry_unavailable"
    elif recommended_profile == active_profile:
        profile_alignment = "aligned"
    else:
        profile_alignment = "action_recommended"

    policy_mode = str(
        policy_mode
        or "observe_only"
    ).strip().lower()

    if policy_mode not in {
        "disabled",
        "observe_only",
        "automatic_control",
    }:
        policy_mode = "observe_only"

    return {
        "schema_version": 1,
        "event_type": "thermal_observer",
        "timestamp": (
            float(timestamp)
            if timestamp is not None
            else time.time()
        ),
        "policy_mode": policy_mode,
        "recommended_profile": recommended_profile,
        "previous_recommended_profile": previous_profile,
        "transition_direction": transition_direction,
        "profile_alignment": profile_alignment,
        "active_profile": active_profile,
        "control_authority": str(
            control_authority
            or "automatic"
        ).strip().lower(),
        "hottest_temperature_c": (
            float(hottest)
            if hottest is not None
            else None
        ),
        "telemetry_valid": telemetry_valid,
        "recommendation_changed": bool(
            getattr(
                recommendation,
                "changed",
                False,
            )
        ),
        "reason": str(
            getattr(
                recommendation,
                "reason",
                "Thermal recommendation unavailable.",
            )
        ),
    }


class ThermalObserverHistory:
    """Append, read, and bound thermal-observer JSONL history."""

    def __init__(
        self,
        path: str | Path = (
            DEFAULT_THERMAL_OBSERVER_HISTORY_PATH
        ),
        *,
        enabled: bool = True,
        maximum_events: int = 1000,
        clock: Callable[[], float] = time.time,
    ):
        self.path = Path(path)
        self.enabled = bool(enabled)
        self.maximum_events = max(
            1,
            int(maximum_events),
        )
        self.clock = clock

    def _normalize(
        self,
        event: Mapping[str, Any],
    ) -> dict[str, Any]:
        normalized = dict(event)

        normalized["schema_version"] = 1
        normalized["event_type"] = (
            "thermal_observer"
        )
        normalized["timestamp"] = float(
            normalized.get(
                "timestamp",
                self.clock(),
            )
        )
        policy_mode = str(
            normalized.get(
                "policy_mode",
                "observe_only",
            )
        ).strip().lower()

        if policy_mode not in {
            "disabled",
            "observe_only",
            "automatic_control",
        }:
            policy_mode = "observe_only"

        normalized["policy_mode"] = policy_mode
        normalized[
            "recommended_profile"
        ] = _safe_profile(
            normalized.get(
                "recommended_profile"
            )
        )
        normalized["active_profile"] = (
            _safe_profile(
                normalized.get(
                    "active_profile"
                )
            )
        )
        normalized[
            "previous_recommended_profile"
        ] = _safe_profile(
            normalized.get(
                "previous_recommended_profile",
                "automatic",
            )
        )

        transition_direction = str(
            normalized.get(
                "transition_direction",
                "steady",
            )
        ).strip().lower()

        if transition_direction not in {
            "steady",
            "upshift",
            "downshift",
        }:
            transition_direction = "steady"

        normalized[
            "transition_direction"
        ] = transition_direction

        profile_alignment = str(
            normalized.get(
                "profile_alignment",
                "telemetry_unavailable",
            )
        ).strip().lower()

        if profile_alignment not in {
            "aligned",
            "action_recommended",
            "telemetry_unavailable",
        }:
            profile_alignment = (
                "telemetry_unavailable"
            )

        normalized[
            "profile_alignment"
        ] = profile_alignment
        normalized["control_authority"] = str(
            normalized.get(
                "control_authority",
                "automatic",
            )
        ).strip().lower()
        normalized["telemetry_valid"] = bool(
            normalized.get(
                "telemetry_valid",
                False,
            )
        )
        normalized[
            "recommendation_changed"
        ] = bool(
            normalized.get(
                "recommendation_changed",
                False,
            )
        )
        normalized["reason"] = str(
            normalized.get(
                "reason",
                "Thermal recommendation unavailable.",
            )
        )

        hottest = normalized.get(
            "hottest_temperature_c"
        )

        try:
            normalized[
                "hottest_temperature_c"
            ] = (
                float(hottest)
                if hottest is not None
                else None
            )
        except (
            TypeError,
            ValueError,
        ):
            normalized[
                "hottest_temperature_c"
            ] = None

        return normalized

    def append(
        self,
        event: Mapping[str, Any],
    ) -> bool:
        if not self.enabled:
            return False

        normalized = self._normalize(
            event
        )

        self.path.parent.mkdir(
            parents=True,
            exist_ok=True,
            mode=0o755,
        )

        with self.path.open(
            "a",
            encoding="utf-8",
        ) as handle:
            handle.write(
                json.dumps(
                    normalized,
                    separators=(",", ":"),
                    sort_keys=True,
                )
                + "\n"
            )
            handle.flush()
            os.fsync(
                handle.fileno()
            )

        self.prune()
        return True

    def read(
        self,
        *,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        try:
            lines = self.path.read_text(
                encoding="utf-8",
            ).splitlines()
        except (
            FileNotFoundError,
            OSError,
        ):
            return []

        events = []

        for line in lines:
            try:
                event = json.loads(
                    line
                )
            except json.JSONDecodeError:
                continue

            if not isinstance(
                event,
                dict,
            ):
                continue

            events.append(
                event
            )

        limit = max(
            0,
            int(limit),
        )

        if limit == 0:
            return []

        return events[-limit:]

    def prune(self) -> int:
        events = self.read(
            limit=self.maximum_events
        )

        if not events:
            return 0

        try:
            current_lines = self.path.read_text(
                encoding="utf-8",
            ).splitlines()
        except (
            FileNotFoundError,
            OSError,
        ):
            return 0

        valid_count = 0

        for line in current_lines:
            try:
                if isinstance(
                    json.loads(line),
                    dict,
                ):
                    valid_count += 1
            except json.JSONDecodeError:
                continue

        if valid_count <= self.maximum_events:
            return valid_count

        self.path.parent.mkdir(
            parents=True,
            exist_ok=True,
            mode=0o755,
        )

        descriptor = None
        temporary_name = None

        try:
            descriptor, temporary_name = (
                tempfile.mkstemp(
                    prefix=f".{self.path.name}.",
                    suffix=".tmp",
                    dir=self.path.parent,
                )
            )

            with os.fdopen(
                descriptor,
                "w",
                encoding="utf-8",
            ) as handle:
                descriptor = None

                for event in events:
                    handle.write(
                        json.dumps(
                            event,
                            separators=(",", ":"),
                            sort_keys=True,
                        )
                        + "\n"
                    )

                handle.flush()
                os.fsync(
                    handle.fileno()
                )

            os.chmod(
                temporary_name,
                0o644,
            )
            os.replace(
                temporary_name,
                self.path,
            )
            temporary_name = None
        finally:
            if descriptor is not None:
                os.close(
                    descriptor
                )

            if temporary_name is not None:
                try:
                    os.unlink(
                        temporary_name
                    )
                except FileNotFoundError:
                    pass

        return len(events)


__all__ = [
    "DEFAULT_THERMAL_OBSERVER_HISTORY_PATH",
    "ThermalObserverHistory",
    "event_from_recommendation",
]
