"""Atomic runtime bridge for the live LCD display contents."""

from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any, Callable, Mapping


DEFAULT_LCD_DISPLAY_STATUS_PATH = Path(
    "/run/truepanel/lcd-display-status.json"
)


class LCDDisplayStatusBridge:
    """Publish and safely read the most recently transmitted LCD frame."""

    def __init__(
        self,
        path: str | Path = DEFAULT_LCD_DISPLAY_STATUS_PATH,
        *,
        clock: Callable[[], float] = time.time,
    ):
        self.path = Path(path)
        self.clock = clock

    @staticmethod
    def _normalize_line(value: Any) -> str:
        if isinstance(value, bytearray):
            value = bytes(value)

        if isinstance(value, bytes):
            text = value.decode(
                "latin-1",
                errors="replace",
            )
        else:
            text = str(
                value
                if value is not None
                else ""
            )

        return text[:16].ljust(16)

    def publish(
        self,
        lines,
        *,
        page: str | None = None,
        source: str = "runtime",
    ) -> dict[str, Any]:
        if not isinstance(
            lines,
            (list, tuple),
        ):
            raise TypeError(
                "LCD display lines must be a list or tuple."
            )

        line1 = self._normalize_line(
            lines[0]
            if len(lines) >= 1
            else ""
        )
        line2 = self._normalize_line(
            lines[1]
            if len(lines) >= 2
            else ""
        )

        payload = {
            "schema_version": 1,
            "timestamp": float(
                self.clock()
            ),
            "display": {
                "line1": line1,
                "line2": line2,
                "page": (
                    str(page)
                    if page is not None
                    else None
                ),
                "source": str(source),
            },
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
            Mapping,
        ):
            return None

        display = payload.get(
            "display"
        )
        timestamp = payload.get(
            "timestamp"
        )

        if not isinstance(
            display,
            Mapping,
        ):
            return None

        try:
            timestamp = float(
                timestamp
            )
        except (
            TypeError,
            ValueError,
        ):
            return None

        age_seconds = max(
            0.0,
            float(self.clock())
            - timestamp,
        )

        return {
            "schema_version": 1,
            "timestamp": timestamp,
            "age_seconds": age_seconds,
            "stale": age_seconds > float(max_age),
            "display": {
                "line1": self._normalize_line(
                    display.get(
                        "line1",
                        "",
                    )
                ),
                "line2": self._normalize_line(
                    display.get(
                        "line2",
                        "",
                    )
                ),
                "page": display.get(
                    "page"
                ),
                "source": str(
                    display.get(
                        "source",
                        "runtime",
                    )
                ),
            },
        }
