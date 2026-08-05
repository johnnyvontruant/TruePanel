"""Read-only bridge for production LCD reader diagnostics."""

from __future__ import annotations

import json
import os
import tempfile
import time
from collections.abc import Callable, Mapping
from contextlib import suppress
from pathlib import Path
from typing import Any

DEFAULT_LCD_READER_STATUS_PATH = Path(
    "/run/truepanel/lcd-reader-status.json"
)


def _safe_int(
    value: Any,
    default: int = 0,
) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _safe_float(
    value: Any,
) -> float | None:
    if value is None:
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class LCDReaderStatusBridge:
    """Atomically publish and safely read LCD reader health."""

    def __init__(
        self,
        path: str | Path = DEFAULT_LCD_READER_STATUS_PATH,
        *,
        clock: Callable[[], float] = time.time,
    ):
        self.path = Path(path)
        self.clock = clock

    def publish(
        self,
        reader: Mapping[str, Any],
    ) -> dict[str, Any]:
        timestamp = float(
            self.clock()
        )

        previous_reader = None

        try:
            previous_payload = json.loads(
                self.path.read_text(
                    encoding="utf-8"
                )
            )
        except (
            FileNotFoundError,
            OSError,
            json.JSONDecodeError,
        ):
            previous_payload = None

        if isinstance(
            previous_payload,
            dict,
        ):
            candidate = previous_payload.get(
                "reader"
            )

            if isinstance(
                candidate,
                dict,
            ):
                previous_reader = candidate

        connected = bool(
            reader.get(
                "connected",
                False,
            )
        )
        thread_alive = bool(
            reader.get(
                "thread_alive",
                False,
            )
        )
        dispatcher_alive = bool(
            reader.get(
                "dispatcher_alive",
                False,
            )
        )
        healthy = bool(
            connected
            and thread_alive
            and dispatcher_alive
        )

        previous_healthy = None
        previous_planned_stop = False

        if previous_reader is not None:
            previous_healthy = bool(
                previous_reader.get(
                    "healthy",
                    False,
                )
            )
            previous_planned_stop = bool(
                previous_reader.get(
                    "stop_requested",
                    False,
                )
            )

        recovery_count = max(
            0,
            _safe_int(
                (
                    previous_reader
                    or {}
                ).get(
                    "recovery_count"
                )
            ),
        )
        last_recovery_at = _safe_float(
            (
                previous_reader
                or {}
            ).get(
                "last_recovery_at"
            )
        )
        last_healthy_at = _safe_float(
            (
                previous_reader
                or {}
            ).get(
                "last_healthy_at"
            )
        )
        episode_started_at = _safe_float(
            (
                previous_reader
                or {}
            ).get(
                "episode_started_at"
            )
        )

        if healthy:
            last_healthy_at = timestamp

        if (
            previous_healthy is False
            and healthy
        ):
            if not previous_planned_stop:
                recovery_count += 1
                last_recovery_at = timestamp

            episode_started_at = timestamp
        elif (
            previous_healthy is not None
            and previous_healthy != healthy
        ) or episode_started_at is None:
            episode_started_at = timestamp

        normalized_reader = {
            "healthy": healthy,
            "last_healthy_at": last_healthy_at,
            "recovery_count": recovery_count,
            "last_recovery_at": last_recovery_at,
            "episode_state": (
                "healthy"
                if healthy
                else "degraded"
            ),
            "episode_started_at": episode_started_at,
            "connected": connected,
            "connection_error": (
                str(
                    reader.get(
                        "connection_error"
                    )
                )
                if reader.get(
                    "connection_error"
                )
                is not None
                else None
            ),
            "port": (
                str(
                    reader.get(
                        "port"
                    )
                )
                if reader.get(
                    "port"
                )
                is not None
                else None
            ),
            "speed": max(
                0,
                _safe_int(
                    reader.get(
                        "speed"
                    )
                ),
            ),
            "thread_alive": thread_alive,
            "dispatcher_alive": dispatcher_alive,
            "stop_requested": bool(
                reader.get(
                    "stop_requested",
                    False,
                )
            ),
            "started_at": _safe_float(
                reader.get(
                    "started_at"
                )
            ),
            "stopped_at": _safe_float(
                reader.get(
                    "stopped_at"
                )
            ),
            "dispatcher_started_at": _safe_float(
                reader.get(
                    "dispatcher_started_at"
                )
            ),
            "dispatcher_stopped_at": _safe_float(
                reader.get(
                    "dispatcher_stopped_at"
                )
            ),
            "dispatcher_events": max(
                0,
                _safe_int(
                    reader.get(
                        "dispatcher_events"
                    )
                ),
            ),
            "dispatch_queue_depth": max(
                0,
                _safe_int(
                    reader.get(
                        "dispatch_queue_depth"
                    )
                ),
            ),
            "replies": max(
                0,
                _safe_int(
                    reader.get(
                        "replies"
                    )
                ),
            ),
            "reader_errors": max(
                0,
                _safe_int(
                    reader.get(
                        "reader_errors"
                    )
                ),
            ),
            "last_reader_error": (
                str(
                    reader.get(
                        "last_reader_error"
                    )
                )
                if reader.get(
                    "last_reader_error"
                )
                is not None
                else None
            ),
            "button_reports": max(
                0,
                _safe_int(
                    reader.get(
                        "button_reports"
                    )
                ),
            ),
            "last_button_mask": max(
                0,
                _safe_int(
                    reader.get(
                        "last_button_mask"
                    )
                ),
            ),
            "last_pressed_button_mask": max(
                0,
                _safe_int(
                    reader.get(
                        "last_pressed_button_mask"
                    )
                ),
            ),
            "last_button_time": _safe_float(
                reader.get(
                    "last_button_time"
                )
            ),
            "callback_count": max(
                0,
                _safe_int(
                    reader.get(
                        "callback_count"
                    )
                ),
            ),
            "callback_errors": max(
                0,
                _safe_int(
                    reader.get(
                        "callback_errors"
                    )
                ),
            ),
            "last_callback_error": (
                str(
                    reader.get(
                        "last_callback_error"
                    )
                )
                if reader.get(
                    "last_callback_error"
                )
                is not None
                else None
            ),
            "last_callback_duration_ms": _safe_float(
                reader.get(
                    "last_callback_duration_ms"
                )
            ),
            "max_callback_duration_ms": _safe_float(
                reader.get(
                    "max_callback_duration_ms"
                )
            ),
            "queued_button_events": max(
                0,
                _safe_int(
                    reader.get(
                        "queued_button_events"
                    )
                ),
            ),
        }

        payload = {
            "schema_version": 1,
            "timestamp": timestamp,
            "reader": normalized_reader,
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

                json.dump(
                    payload,
                    handle,
                    sort_keys=True,
                )
                handle.write("\n")
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

            return payload
        finally:
            if descriptor is not None:
                os.close(
                    descriptor
                )

            if temporary_name is not None:
                with suppress(
                    FileNotFoundError
                ):
                    os.unlink(
                        temporary_name
                    )

    def read(
        self,
        *,
        max_age: float = 15.0,
    ) -> dict[str, Any] | None:
        try:
            payload = json.loads(
                self.path.read_text(
                    encoding="utf-8"
                )
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

        reader = payload.get(
            "reader"
        )

        if not isinstance(
            reader,
            dict,
        ):
            return None

        try:
            timestamp = float(
                payload["timestamp"]
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
            "schema_version": _safe_int(
                payload.get(
                    "schema_version",
                    1,
                ),
                1,
            ),
            "timestamp": timestamp,
            "age_seconds": age,
            "reader": dict(reader),
        }


__all__ = [
    "DEFAULT_LCD_READER_STATUS_PATH",
    "LCDReaderStatusBridge",
]
