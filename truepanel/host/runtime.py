"""
Lifecycle ownership for TruePanel privileged host services.

HostAgentRuntime groups the privileged fan command service and fan-control
runtime behind one lifecycle boundary. LCD application command handling lives
outside this hardware-ownership boundary.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

LOGGER = logging.getLogger(__name__)


class HostAgentRuntime:
    """Own the lifecycle of TruePanel's privileged local host services."""

    def __init__(
        self,
        *,
        fan_runtime: Any,
        safety: Any,
        fan_server_factory: Callable[[], Any | None],
        ownership_guard: Any | None = None,
        fan_status_reader: Callable[..., Any] | None = None,
        fan_reconciliation: Any | None = None,
        thermal_lifecycle: Any | None = None,
    ):
        self._fan_runtime = fan_runtime
        self._safety = safety
        self._ownership_guard = ownership_guard
        self._ownership_acquired = False
        self._fan_status_reader = fan_status_reader
        self._fan_reconciliation = fan_reconciliation
        self._thermal_lifecycle = thermal_lifecycle
        self._fan_server_factory = fan_server_factory

        self._fan_server = None
        self._started = False
        self._shutdown = False

    @property
    def safety(self) -> Any:
        """Return the Host Agent safety coordinator."""

        return self._safety

    def _require_hardware_ownership(self) -> None:
        """Refuse actuating Host work unless this runtime owns hardware."""

        if (
            self._ownership_guard is not None
            and not self._ownership_acquired
        ):
            raise RuntimeError(
                "HostAgentRuntime does not own Host hardware"
            )

    def read_fan_status(
        self,
        *,
        max_age: float = 30.0,
    ) -> Any:
        """Read the latest Host-published fan/thermal status snapshot."""

        if self._fan_status_reader is None:
            return None

        return self._fan_status_reader(
            max_age=max_age
        )

    def fan_telemetry(self) -> Any:
        """Return the Host-owned fan/thermal telemetry snapshot."""

        return self._safety.telemetry()

    def publish_fan_status(
        self,
        reason: str | None = None,
    ) -> Any:
        """Publish the Host-owned fan/thermal status snapshot."""

        return self._safety.publish_status(
            reason=reason
        )

    def observe_thermal(
        self,
        telemetry: Any = None,
    ) -> Any:
        """Evaluate Host thermal guidance without granting authority."""

        if self._fan_reconciliation is None:
            return None

        return self._fan_reconciliation.observe(
            telemetry
        )

    def reconcile_fans(self) -> Any | None:
        """Run one Host-owned fan/thermal reconciliation cycle."""

        self._require_hardware_ownership()

        if self._fan_reconciliation is None:
            return None

        return self._fan_reconciliation.reconcile()

    def service_cycle(
        self,
        *,
        reconcile: bool = True,
        publish_reason: str | None = None,
    ) -> dict[str, Any]:
        """
        Run one Host service cycle while preserving legacy loop semantics.

        Reconciliation is privileged and therefore requires Host ownership.
        Observation and status publication remain safe for pre-start priming.
        Reconciliation failures are isolated so guidance and status still
        refresh, matching the existing LCD runtime behavior.
        """

        reconciliation = None

        if reconcile:
            self._require_hardware_ownership()
            try:
                reconciliation = self.reconcile_fans()
            except Exception:
                LOGGER.exception(
                    "Fan-control reconciliation failed"
                )

        recommendation = self.observe_thermal()
        status = self.publish_fan_status(
            reason=publish_reason
        )

        return {
            "reconciliation": reconciliation,
            "recommendation": recommendation,
            "status": status,
        }

    def end_supervised_thermal_session(
        self,
        reason: str,
        *,
        lifecycle_action: str,
        telemetry: Any = None,
    ) -> Any:
        """End one Host-owned supervised thermal session."""

        self._require_hardware_ownership()

        if self._thermal_lifecycle is None:
            return None

        return self._thermal_lifecycle.end_supervised_session(
            reason,
            lifecycle_action=lifecycle_action,
            telemetry=telemetry,
        )

    def supervised_thermal_session_active(self) -> bool:
        """Return whether Host thermal supervision is active."""

        if self._thermal_lifecycle is None:
            return False

        return (
            self._thermal_lifecycle
            .supervised_session_active()
        )

    def end_bounded_automatic_lease(
        self,
        reason: str,
        *,
        lifecycle_action: str,
        telemetry: Any = None,
        restore: bool = True,
    ) -> Any:
        """End one Host-owned bounded automatic-control lease."""

        self._require_hardware_ownership()

        if self._thermal_lifecycle is None:
            return None

        return (
            self._thermal_lifecycle
            .end_bounded_automatic_lease(
                reason,
                lifecycle_action=lifecycle_action,
                telemetry=telemetry,
                restore=restore,
            )
        )

    @property
    def started(self) -> bool:
        return self._started

    @property
    def fan_server(self) -> Any | None:
        return self._fan_server

    def start(self) -> None:
        """
        Start privileged Host command services.

        Starting twice is harmless. If startup fails, all resources already
        acquired by this runtime are released before the exception is raised.
        """

        if self._started:
            return

        if self._shutdown:
            raise RuntimeError(
                "HostAgentRuntime cannot restart after shutdown"
            )

        if self._ownership_guard is not None:
            self._ownership_guard.acquire()
            self._ownership_acquired = True

        try:
            self._fan_server = (
                self._fan_server_factory()
            )

            if self._fan_server is not None:
                self._fan_server.start()

            self._started = True
        except Exception:
            LOGGER.exception(
                "Host Agent startup failed"
            )

            self.shutdown()
            raise

    def shutdown(self) -> None:
        """
        Stop privileged command services and restore the fan runtime.

        The fan command socket is stopped before automatic restoration so no
        new hardware commands can enter while restoration is occurring.
        """

        if self._shutdown:
            return

        self._shutdown = True

        if self._fan_server is not None:
            try:
                self._fan_server.stop()
            except Exception:
                LOGGER.exception(
                    "Fan command server shutdown failed"
                )
            finally:
                self._fan_server = None

        if (
            self._ownership_guard is None
            or self._ownership_acquired
        ):
            try:
                self._fan_runtime.shutdown()
            except Exception:
                LOGGER.exception(
                    "Fan-control runtime shutdown failed"
                )

        if self._ownership_acquired:
            try:
                self._ownership_guard.release()
            except Exception:
                LOGGER.exception(
                    "Host ownership release failed"
                )
            finally:
                self._ownership_acquired = False

        self._started = False


__all__ = [
    "HostAgentRuntime",
]
