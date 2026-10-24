"""Host-owned polling service for Loadmaster physical Copy confirmation."""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from typing import Any

from truepanel.cargo.copy_button import (
    CopyButtonConfirmation,
    LoadmasterCopyButtonGate,
    LoadmasterPhysicalPreflight,
)

LOGGER = logging.getLogger(__name__)

DEFAULT_COPY_BUTTON_POLL_SECONDS = 0.020


class LoadmasterCopyButtonService:
    """Own the Copy-button reader and confirmation gate lifecycle.

    This service creates confirmation evidence only. It has no mount, copy,
    delete, sync, unmount, or transfer-executor dependency.
    """

    def __init__(
        self,
        *,
        reader: Any,
        gate: LoadmasterCopyButtonGate | None = None,
        on_confirmation: Callable[
            [CopyButtonConfirmation],
            None,
        ] | None = None,
        event_recorder: Callable[
            [dict[str, object]],
            None,
        ] | None = None,
        poll_seconds: float = DEFAULT_COPY_BUTTON_POLL_SECONDS,
        preflight_provider: Callable[[], LoadmasterPhysicalPreflight | None] | None = None,
    ) -> None:
        if poll_seconds <= 0:
            raise ValueError("poll_seconds must be positive")

        self.reader = reader
        self.gate = gate or LoadmasterCopyButtonGate(
            read_level=reader.read_level
        )
        self.on_confirmation = on_confirmation
        self.event_recorder = event_recorder
        self.poll_seconds = float(poll_seconds)
        self.preflight_provider = preflight_provider

        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._started = False
        self._last_confirmation: CopyButtonConfirmation | None = None
        self._last_error: str | None = None
        self._signal_samples = 0
        self._signal_edges = 0
        self._signal_last_level: int | None = None
        self._signal_last_edge_at: float | None = None
        self._signal_low_samples = 0
        self._signal_high_samples = 0

        # Observe the SAME read used by the gate; never read GPIO a second time.
        original_read_level = self.gate._read_level

        def observed_read_level():
            value = original_read_level()
            if isinstance(value, (int, bool)) and int(value) in (0, 1):
                level = int(value)
                with self._lock:
                    self._signal_samples += 1
                    if level == 0:
                        self._signal_low_samples += 1
                    else:
                        self._signal_high_samples += 1
                    if self._signal_last_level is not None and level != self._signal_last_level:
                        self._signal_edges += 1
                        self._signal_last_edge_at = time.time()
                    self._signal_last_level = level
            return value

        self.gate._read_level = observed_read_level

    @property
    def started(self) -> bool:
        with self._lock:
            return self._started

    def arm(
        self,
        preflight: LoadmasterPhysicalPreflight,
    ) -> None:
        """Arm one already-verified Loadmaster physical preflight."""
        with self._lock:
            self.gate.arm(preflight)
            self._record(
                {
                    "event": "armed",
                    **self.gate.armed_snapshot(),
                }
            )

    def disarm(self, *, reason: str = "operator") -> None:
        """Fail closed and discard current confirmation authority."""
        with self._lock:
            snapshot = self.gate.armed_snapshot()
            self.gate.disarm()
            self._record(
                {
                    "event": "disarmed",
                    "reason": str(reason),
                    **snapshot,
                }
            )

    def snapshot(self) -> dict[str, object]:
        with self._lock:
            payload = {
                **self.gate.armed_snapshot(),
                "service_started": self._started,
                "poll_seconds": self.poll_seconds,
                "last_error": self._last_error,
                "signal": {
                    "samples": self._signal_samples,
                    "edges": self._signal_edges,
                    "low_samples": self._signal_low_samples,
                    "high_samples": self._signal_high_samples,
                    "last_level": self._signal_last_level,
                    "last_edge_at": self._signal_last_edge_at,
                },
                "last_confirmation": (
                    self._last_confirmation.public_dict()
                    if self._last_confirmation is not None
                    else None
                ),
            }
            return payload

    def start(self) -> None:
        with self._lock:
            if self._started:
                return

            self._stop.clear()
            self._thread = threading.Thread(
                target=self._run,
                name="truepanel-loadmaster-copy-button",
                daemon=True,
            )
            self._thread.start()
            self._started = True
            self._record(
                {
                    "event": "service_started",
                    **self.gate.armed_snapshot(),
                }
            )

    def stop(self) -> None:
        with self._lock:
            if not self._started:
                self._close_reader()
                return

            self._stop.set()
            thread = self._thread

        if thread is not None:
            thread.join(timeout=max(1.0, self.poll_seconds * 10))

        with self._lock:
            self.gate.disarm()
            self._thread = None
            self._started = False
            self._close_reader()
            self._record(
                {
                    "event": "service_stopped",
                    **self.gate.armed_snapshot(),
                }
            )

    def _run(self) -> None:
        while not self._stop.wait(self.poll_seconds):
            try:
                # Only an independently verified source may arm the gate.
                if self.preflight_provider is not None:
                    preflight = self.preflight_provider()
                    with self._lock:
                        armed = self.gate.armed_snapshot()
                        if preflight is None or not preflight.ready:
                            self.gate.disarm()
                        elif not armed["armed"]:
                            try:
                                self.gate.arm(preflight)
                            except ValueError:
                                self.gate.disarm()
                        elif (
                            armed["plan_digest"] != preflight.plan_digest
                            or armed["cartridge_uuid"] != preflight.cartridge_uuid
                            or armed["cartridge_id"] != preflight.cartridge_id
                        ):
                            self.gate.disarm()
                            try:
                                self.gate.arm(preflight)
                            except ValueError:
                                pass
                confirmation = self.gate.poll()
            except Exception as error:
                LOGGER.exception(
                    "Loadmaster Copy-button polling failed"
                )
                with self._lock:
                    self._last_error = (
                        f"{type(error).__name__}: {error}"
                    )
                    self.gate.disarm()
                    self._record(
                        {
                            "event": "reader_error",
                            "error": self._last_error,
                            **self.gate.armed_snapshot(),
                        }
                    )
                self._stop.set()
                return

            if confirmation is None:
                continue

            with self._lock:
                self._last_confirmation = confirmation
                self.gate.disarm()
                self._record(
                    {
                        "event": "confirmed",
                        **confirmation.public_dict(),
                    }
                )

            if self.on_confirmation is not None:
                try:
                    self.on_confirmation(confirmation)
                except Exception:
                    LOGGER.exception(
                        "Loadmaster Copy confirmation callback failed"
                    )

    def _record(self, event: dict[str, object]) -> None:
        if self.event_recorder is None:
            return
        try:
            self.event_recorder(dict(event))
        except Exception:
            LOGGER.exception(
                "Could not record Loadmaster Copy-button event"
            )

    def _close_reader(self) -> None:
        close = getattr(self.reader, "close", None)
        if callable(close):
            try:
                close()
            except Exception:
                LOGGER.exception(
                    "Loadmaster Copy-button reader close failed"
                )


__all__ = [
    "DEFAULT_COPY_BUTTON_POLL_SECONDS",
    "LoadmasterCopyButtonService",
]