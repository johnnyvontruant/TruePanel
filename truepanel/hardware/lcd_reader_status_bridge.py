"""Read-only bridge for production LCD reader diagnostics."""

from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any, Callable, Mapping


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

        normalized_reader = {
            "thread_alive": bool(
                reader.get(
                    "thread_alive",
                    False,
                )
            ),
            "dispatcher_alive": bool(
                reader.get(
                    "dispatcher_alive",
                    False,
                )
            ),
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
                try:
                    os.unlink(
                        temporary_name
                    )
                except FileNotFoundError:
                    pass

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
