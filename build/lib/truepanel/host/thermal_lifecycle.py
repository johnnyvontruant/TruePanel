"""Host-owned thermal session and bounded-lease lifecycle wiring."""

from __future__ import annotations

from typing import Any


class HostThermalLifecycleCoordinator:
    """Bind thermal-authority lifecycle operations to Host safety services."""

    def __init__(
        self,
        *,
        thermal_authority: Any,
        safety: Any,
        record_commissioning_event: Any,
    ):
        self._thermal_authority = thermal_authority
        self._safety = safety
        self._record_commissioning_event = (
            record_commissioning_event
        )

    def end_supervised_session(
        self,
        reason: str,
        *,
        lifecycle_action: str,
        telemetry: Any = None,
    ) -> Any:
        """End a supervised thermal session through Host-owned callbacks."""

        return self._thermal_authority.end_supervised_session(
            reason,
            lifecycle_action=lifecycle_action,
            telemetry=telemetry,
            telemetry_provider=self._safety.telemetry,
            restore_automatic=self._safety.restore_automatic,
            publish_status=self._safety.publish_status,
            record_commissioning_event=(
                self._record_commissioning_event
            ),
        )

    def supervised_session_active(self) -> bool:
        """Return whether the Host thermal authority has a live session."""

        return bool(
            self._thermal_authority
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
        """End bounded automatic control through Host-owned callbacks."""

        return self._thermal_authority.end_automatic_lease(
            reason,
            lifecycle_action=lifecycle_action,
            telemetry=telemetry,
            telemetry_provider=self._safety.telemetry,
            restore_automatic=self._safety.restore_automatic,
            publish_status=self._safety.publish_status,
            record_commissioning_event=(
                self._record_commissioning_event
            ),
            restore=restore,
        )


__all__ = [
    "HostThermalLifecycleCoordinator",
]
