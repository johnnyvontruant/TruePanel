"""
One-way runtime status bridge for TruePanel fan control.

The root-owned LCD runtime publishes JSON status atomically. Mission Control
may read the file, but this bridge contains no command or hardware-control
surface.
"""

from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any, Callable, Mapping


DEFAULT_FAN_CONTROL_STATUS_PATH = Path(
    "/run/truepanel/fan-control-status.json"
)


def _safe_profile(
    value: Any,
) -> str:
    profile = str(
        value
        or "automatic"
    ).strip().lower()

    allowed = {
        "automatic",
        "quiet",
        "balanced",
        "cooling_boost",
        "afterburners",
    }

    if profile not in allowed:
        return "automatic"

    return profile


class FanControlStatusBridge:
    """Atomically publish and safely read fan-control runtime status."""

    def __init__(
        self,
        path: str | Path = DEFAULT_FAN_CONTROL_STATUS_PATH,
        *,
        clock: Callable[[], float] = time.time,
    ):
        self.path = Path(
            path
        )
        self.clock = clock

    def publish(
        self,
        payload: Mapping[str, Any],
    ) -> dict[str, Any]:
        now = float(
            self.clock()
        )

        normalized = {
            "schema_version": 1,
            "timestamp": now,
            "enabled": bool(
                payload.get(
                    "enabled",
                    False,
                )
            ),
            "connected": bool(
                payload.get(
                    "connected",
                    False,
                )
            ),
            "active_profile": _safe_profile(
                payload.get(
                    "active_profile"
                )
            ),
            "requested_profile": _safe_profile(
                payload.get(
                    "requested_profile"
                )
            ),
            "remaining_seconds": (
                float(
                    payload[
                        "remaining_seconds"
                    ]
                )
                if payload.get(
                    "remaining_seconds"
                )
                is not None
                else None
            ),
            "last_reason": str(
                payload.get(
                    "last_reason",
                    "Fan control status unavailable.",
                )
            ),
            "control_authority": str(
                payload.get(
                    "control_authority",
                    "automatic",
                )
            ).strip().lower(),
            "safety_hold": bool(
                payload.get(
                    "safety_hold",
                    False,
                )
            ),
            "recovery_pending": bool(
                payload.get(
                    "recovery_pending",
                    False,
                )
            ),
            "recovery_healthy_cycles": max(
                0,
                int(
                    payload.get(
                        "recovery_healthy_cycles",
                        0,
                    )
                    or 0
                ),
            ),
            "recovery_required_cycles": max(
                1,
                int(
                    payload.get(
                        "recovery_required_cycles",
                        3,
                    )
                    or 3
                ),
            ),
        }

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
                    prefix=(
                        f".{self.path.name}."
                    ),
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

                json.dump(
                    normalized,
                    handle,
                    sort_keys=True,
                )
                handle.write(
                    "\n"
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

            return normalized
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

    def read(
        self,
        *,
        max_age: float = 30.0,
    ) -> dict[str, Any] | None:
        try:
            raw = self.path.read_text(
                encoding="utf-8"
            )
            payload = json.loads(
                raw
            )
        except (
            FileNotFoundError,
            OSError,
            json.JSONDecodeError,
        ):
            return None

        if not isinstance(
            payload,
            dict,
        ):
            return None

        try:
            timestamp = float(
                payload[
                    "timestamp"
                ]
            )
        except (
            KeyError,
            TypeError,
            ValueError,
        ):
            return None

        age = max(
            0.0,
            float(
                self.clock()
            )
            - timestamp,
        )

        if age > max(
            0.0,
            float(max_age),
        ):
            return None

        return {
            "schema_version": int(
                payload.get(
                    "schema_version",
                    1,
                )
            ),
            "timestamp": timestamp,
            "age_seconds": age,
            "enabled": bool(
                payload.get(
                    "enabled",
                    False,
                )
            ),
            "connected": bool(
                payload.get(
                    "connected",
                    False,
                )
            ),
            "active_profile": _safe_profile(
                payload.get(
                    "active_profile"
                )
            ),
            "requested_profile": _safe_profile(
                payload.get(
                    "requested_profile"
                )
            ),
            "remaining_seconds": (
                float(
                    payload[
                        "remaining_seconds"
                    ]
                )
                if payload.get(
                    "remaining_seconds"
                )
                is not None
                else None
            ),
            "last_reason": str(
                payload.get(
                    "last_reason",
                    "Fan control status unavailable.",
                )
            ),
            "control_authority": str(
                payload.get(
                    "control_authority",
                    "automatic",
                )
            ).strip().lower(),
            "safety_hold": bool(
                payload.get(
                    "safety_hold",
                    False,
                )
            ),
            "recovery_pending": bool(
                payload.get(
                    "recovery_pending",
                    False,
                )
            ),
            "recovery_healthy_cycles": max(
                0,
                int(
                    payload.get(
                        "recovery_healthy_cycles",
                        0,
                    )
                    or 0
                ),
            ),
            "recovery_required_cycles": max(
                1,
                int(
                    payload.get(
                        "recovery_required_cycles",
                        3,
                    )
                    or 3
                ),
            ),
        }


__all__ = [
    "DEFAULT_FAN_CONTROL_STATUS_PATH",
    "FanControlStatusBridge",
]
