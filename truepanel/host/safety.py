"""
Privileged safety coordination for the TruePanel Host Agent.

This module owns host-side safety operations that must remain available
independently of presentation-layer behavior.

Hardware authority is still enforced by the existing fan-control runtime and
its interlocks. This coordinator does not bypass those protections.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any


class HostAgentSafetyCoordinator:
    """
    Coordinate Host Agent safety services around the guarded fan runtime.

    The coordinator centralizes telemetry, status publication, event history,
    thermal command dispatch, and synchronous restoration to motherboard
    Automatic control.
    """

    def __init__(
        self,
        *,
        fan_runtime: Any,
        telemetry_provider: Callable[
            [],
            Mapping[str, Any],
        ],
        status_publisher: Callable[..., Any] | None = None,
        event_recorder: Callable[
            [
                Any,
                Mapping[str, Any],
                str,
            ],
            None,
        ] | None = None,
        thermal_control_handler: Callable[
            [str],
            Mapping[str, Any],
        ] | None = None,
    ):
        self._fan_runtime = fan_runtime
        self._telemetry_provider = telemetry_provider
        self._status_publisher = status_publisher
        self._event_recorder = event_recorder
        self._thermal_control_handler = (
            thermal_control_handler
        )

    @property
    def fan_runtime(self) -> Any:
        return self._fan_runtime

    def telemetry(self) -> Mapping[str, Any]:
        """Return the current guarded fan/thermal telemetry snapshot."""

        return self._telemetry_provider()

    def publish_status(
        self,
        reason: str | None = None,
    ) -> Any:
        """Publish Host Agent fan-control state when configured."""

        if self._status_publisher is None:
            return None

        if reason is None:
            return self._status_publisher()

        return self._status_publisher(
            reason=reason
        )

    def record_event(
        self,
        decision: Any,
        telemetry: Mapping[str, Any],
        *,
        source: str,
    ) -> None:
        """Record one authoritative fan-control decision."""

        if self._event_recorder is None:
            return

        self._event_recorder(
            decision,
            telemetry,
            source,
        )

    def handle_thermal_control(
        self,
        action: str,
    ) -> Mapping[str, Any]:
        """Dispatch a guarded thermal-control request."""

        if self._thermal_control_handler is None:
            return {
                "ok": False,
                "status": "thermal_control_unavailable",
                "message": (
                    "Thermal control is unavailable."
                ),
            }

        return self._thermal_control_handler(
            action
        )

    def reconcile(
        self,
        *,
        telemetry: Mapping[str, Any] | None = None,
        source_classifier: Callable[
            [Any],
            str,
        ] | None = None,
    ) -> tuple[
        Any | None,
        Mapping[str, Any],
    ]:
        """
        Run one authoritative Host Agent fan-safety cycle.

        Existing dead-man, emergency, and recovery behavior receives first
        refusal before thermal-control reconciliation is allowed to proceed.
        """

        current_telemetry = (
            telemetry
            if telemetry is not None
            else self.telemetry()
        )

        if not self._fan_runtime.connected:
            return (
                None,
                current_telemetry,
            )

        service = getattr(
            self._fan_runtime,
            "service",
            None,
        )

        if service is None:
            return (
                None,
                current_telemetry,
            )

        decision = service.tick(
            fan_status=current_telemetry.get(
                "fan_status",
                {},
            ),
            temperatures_c=current_telemetry.get(
                "temperatures_c",
                (),
            ),
            telemetry_fresh=bool(
                current_telemetry.get(
                    "telemetry_fresh",
                    False,
                )
            ),
        )

        if decision is None:
            return (
                None,
                current_telemetry,
            )

        post_transition_telemetry = (
            self.telemetry()
        )

        source = (
            source_classifier(
                decision
            )
            if source_classifier is not None
            else "safety"
        )

        self.record_event(
            decision,
            post_transition_telemetry,
            source=source,
        )

        return (
            decision,
            post_transition_telemetry,
        )

    def restore_automatic(
        self,
        reason: str,
        *,
        telemetry: Mapping[str, Any] | None = None,
    ) -> Any | None:
        """
        Restore controlled fan channels to motherboard Automatic.

        Restoration uses the existing guarded runtime service. If the runtime
        already reports motherboard Automatic authority, no command is issued.
        """

        current_telemetry = (
            telemetry
            if telemetry is not None
            else self.telemetry()
        )

        runtime_status = (
            self._fan_runtime.status_payload()
        )

        if (
            runtime_status.get(
                "active_profile"
            )
            == "automatic"
            and runtime_status.get(
                "control_authority"
            )
            == "automatic"
        ):
            return None

        service = getattr(
            self._fan_runtime,
            "service",
            None,
        )

        if service is None:
            return None

        decision = service.request_profile(
            "automatic",
            fan_status=(
                current_telemetry.get(
                    "fan_status",
                    {},
                )
            ),
            temperatures_c=(
                current_telemetry.get(
                    "temperatures_c",
                    (),
                )
            ),
            telemetry_fresh=bool(
                current_telemetry.get(
                    "telemetry_fresh",
                    False,
                )
            ),
        )

        self.record_event(
            decision,
            self.telemetry(),
            source="thermal_policy",
        )

        self.publish_status(
            reason=reason
        )

        return decision


__all__ = [
    "HostAgentSafetyCoordinator",
]
