"""Host-owned fan and thermal reconciliation orchestration."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


class HostFanReconciliationCoordinator:
    """
    Coordinate one guarded fan/thermal reconciliation cycle.

    Fan safety always receives first refusal. Thermal authority is evaluated
    only after the safety coordinator reports no control-state transition.
    """

    def __init__(
        self,
        *,
        fan_runtime: Any,
        safety: Any,
        thermal_observer: Any,
        thermal_authority: Any,
        fan_event_source: Callable[[Any], str],
        record_fan_event: Callable[..., Any],
        record_commissioning_event: Callable[..., Any],
    ):
        self._fan_runtime = fan_runtime
        self._safety = safety
        self._thermal_observer = thermal_observer
        self._thermal_authority = thermal_authority
        self._fan_event_source = fan_event_source
        self._record_fan_event = record_fan_event
        self._record_commissioning_event = (
            record_commissioning_event
        )

    def reconcile(self) -> Any | None:
        """Run one Host-owned fan safety and thermal-control cycle."""

        if not self._fan_runtime.connected:
            return None

        telemetry = self._safety.telemetry()
        recommendation = self._thermal_observer.observe(
            telemetry
        )

        decision, safety_telemetry = self._safety.reconcile(
            telemetry=telemetry,
            source_classifier=self._fan_event_source,
        )

        if decision is not None:
            self._thermal_authority.handle_fan_safety_transition(
                telemetry=safety_telemetry,
                telemetry_provider=self._safety.telemetry,
                restore_automatic=self._safety.restore_automatic,
                publish_status=self._safety.publish_status,
                record_commissioning_event=(
                    self._record_commissioning_event
                ),
            )
            return decision

        return self._thermal_authority.reconcile(
            recommendation,
            telemetry=telemetry,
            runtime_status_provider=(
                self._fan_runtime.status_payload
            ),
            telemetry_provider=self._safety.telemetry,
            restore_automatic=self._safety.restore_automatic,
            publish_status=self._safety.publish_status,
            record_fan_event=self._record_fan_event,
            record_commissioning_event=(
                self._record_commissioning_event
            ),
        )


__all__ = [
    "HostFanReconciliationCoordinator",
]
