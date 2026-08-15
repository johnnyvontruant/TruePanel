"""Interpret existing TruePanel telemetry into operator-facing health states."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable


class HealthState(str, Enum):
    """Normalized TruePanel health states."""

    NOMINAL = "NOMINAL"
    ATTENTION = "ATTENTION"
    DEGRADED = "DEGRADED"
    CRITICAL = "CRITICAL"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class HealthResult:
    """One interpreted health result."""

    state: HealthState
    summary: str
    reason: str
    recommended_action: str

    def as_dict(self) -> dict[str, str]:
        return {
            "state": self.state.value,
            "summary": self.summary,
            "reason": self.reason,
            "recommended_action": self.recommended_action,
        }


_SEVERITY = {
    HealthState.NOMINAL: 0,
    HealthState.ATTENTION: 1,
    HealthState.DEGRADED: 2,
    HealthState.CRITICAL: 3,
}


class HealthEvaluator:
    """Correlate existing read-only telemetry without inventing new thresholds."""

    subsystem_order = (
        "cooling",
        "thermal",
        "storage",
        "network",
        "front_panel",
        "services",
    )

    def evaluate(
        self,
        *,
        fans: dict[str, Any] | None = None,
        storage: dict[str, Any] | None = None,
        network: list[dict[str, Any]] | None = None,
        lcd: dict[str, Any] | None = None,
        capabilities: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        subsystems = {
            "cooling": self._cooling(fans or {}),
            "thermal": self._thermal(fans or {}),
            "storage": self._storage(storage or {}),
            "network": self._network(network or []),
            "front_panel": self._front_panel(lcd or {}),
            "services": self._services(capabilities or {}),
        }

        overall = self.aggregate(subsystems.values())
        unknown = sum(
            result.state is HealthState.UNKNOWN
            for result in subsystems.values()
        )

        return {
            "state": overall.state.value,
            "summary": overall.summary,
            "reason": overall.reason,
            "recommended_action": overall.recommended_action,
            "unknown_subsystems": unknown,
            "subsystems": {
                name: subsystems[name].as_dict()
                for name in self.subsystem_order
            },
        }

    @staticmethod
    def aggregate(results: Iterable[HealthResult]) -> HealthResult:
        results = tuple(results)
        known = [
            result
            for result in results
            if result.state is not HealthState.UNKNOWN
        ]

        if not known:
            return HealthResult(
                HealthState.UNKNOWN,
                "Health unavailable",
                "No subsystem currently has enough trustworthy telemetry to establish overall health.",
                "Verify TruePanel telemetry sources and service status.",
            )

        worst = max(
            known,
            key=lambda result: _SEVERITY[result.state],
        )

        if worst.state is HealthState.NOMINAL:
            return HealthResult(
                HealthState.NOMINAL,
                "System nominal",
                "All evaluated subsystems with trustworthy telemetry are nominal.",
                "No operator action required.",
            )

        return HealthResult(
            worst.state,
            worst.summary,
            worst.reason,
            worst.recommended_action,
        )

    @staticmethod
    def _cooling(fans: dict[str, Any]) -> HealthResult:
        if not fans.get("available"):
            return HealthResult(
                HealthState.UNKNOWN,
                "Cooling telemetry unavailable",
                "TruePanel does not currently have trustworthy fan telemetry.",
                "Verify the fan telemetry provider and hardware capability.",
            )

        monitored = [
            channel
            for channel in fans.get("channels", [])
            if isinstance(channel, dict)
            and channel.get("monitored")
        ]

        if not monitored:
            return HealthResult(
                HealthState.UNKNOWN,
                "Cooling monitoring unconfigured",
                "Fan telemetry is available but no channels are marked as monitored.",
                "Review the configured monitored fan channels.",
            )

        failed = [
            channel
            for channel in monitored
            if channel.get("alarm") is True
            or int(channel.get("rpm", 0) or 0) <= 0
        ]

        if failed:
            labels = ", ".join(
                str(channel.get("label") or f"Fan {channel.get('number', '?')}")
                for channel in failed
            )
            return HealthResult(
                HealthState.DEGRADED,
                "Cooling degraded",
                f"Monitored fan fault detected: {labels}.",
                "Inspect the affected fan and confirm chassis temperatures remain safe.",
            )

        return HealthResult(
            HealthState.NOMINAL,
            "Cooling nominal",
            "All monitored fans report healthy telemetry.",
            "No operator action required.",
        )

    @staticmethod
    def _thermal(fans: dict[str, Any]) -> HealthResult:
        control = fans.get("control")
        if not isinstance(control, dict):
            return HealthResult(
                HealthState.UNKNOWN,
                "Thermal state unavailable",
                "Thermal control status is not present in the current fan telemetry payload.",
                "Verify the fan-control status bridge.",
            )

        if control.get("safety_hold"):
            return HealthResult(
                HealthState.DEGRADED,
                "Thermal safety hold active",
                str(control.get("thermal_control_reason") or control.get("last_reason") or "TruePanel has placed thermal control in a safety hold."),
                "Review thermal telemetry and restore safe automatic authority only after the hold condition is resolved.",
            )

        if control.get("recovery_pending"):
            return HealthResult(
                HealthState.ATTENTION,
                "Thermal recovery pending",
                str(control.get("thermal_control_reason") or control.get("last_reason") or "Thermal control is waiting for healthy recovery cycles."),
                "Continue monitoring until recovery criteria are satisfied.",
            )

        if not control.get("available", fans.get("available", False)):
            return HealthResult(
                HealthState.UNKNOWN,
                "Thermal control unavailable",
                "The fan controller is not currently available to the thermal status bridge.",
                "Verify the fan controller and telemetry bridge.",
            )

        return HealthResult(
            HealthState.NOMINAL,
            "Thermal state nominal",
            "No thermal safety hold or recovery condition is active.",
            "No operator action required.",
        )

    @staticmethod
    def _storage(storage: dict[str, Any]) -> HealthResult:
        pools = [
            pool
            for pool in storage.get("pools", [])
            if isinstance(pool, dict)
        ]

        if not pools:
            return HealthResult(
                HealthState.UNKNOWN,
                "Storage health unavailable",
                "No pool health records are present in the current snapshot.",
                "Verify TrueNAS pool telemetry.",
            )

        critical = []
        degraded = []
        attention = []

        for pool in pools:
            name = str(pool.get("name") or "Unnamed pool")
            health = str(pool.get("health") or "UNKNOWN").upper()

            if health == "ONLINE":
                continue
            if health in {"FAULTED", "UNAVAIL", "OFFLINE", "REMOVED"}:
                critical.append(f"{name} ({health})")
            elif health == "DEGRADED":
                degraded.append(f"{name} ({health})")
            else:
                attention.append(f"{name} ({health})")

        if critical:
            return HealthResult(
                HealthState.CRITICAL,
                "Storage critical",
                "Critical pool state detected: " + ", ".join(critical) + ".",
                "Open TrueNAS storage status immediately and investigate the affected pool.",
            )

        if degraded:
            return HealthResult(
                HealthState.DEGRADED,
                "Storage degraded",
                "Degraded pool state detected: " + ", ".join(degraded) + ".",
                "Review the affected pool and restore redundancy as soon as practical.",
            )

        if attention:
            return HealthResult(
                HealthState.ATTENTION,
                "Storage needs attention",
                "Non-nominal pool state detected: " + ", ".join(attention) + ".",
                "Review the affected pool in TrueNAS before taking corrective action.",
            )

        return HealthResult(
            HealthState.NOMINAL,
            "Storage nominal",
            "All reported pools are ONLINE.",
            "No operator action required.",
        )

    @staticmethod
    def _network(network: list[dict[str, Any]]) -> HealthResult:
        interfaces = [
            interface
            for interface in network
            if isinstance(interface, dict)
        ]

        if not interfaces:
            return HealthResult(
                HealthState.UNKNOWN,
                "Network health unavailable",
                "No network interface records are present in the current snapshot.",
                "Verify network telemetry discovery.",
            )

        primary = [
            interface
            for interface in interfaces
            if interface.get("primary")
        ]

        if primary:
            if any(interface.get("link_up") for interface in primary):
                return HealthResult(
                    HealthState.NOMINAL,
                    "Network nominal",
                    "The primary network interface is up.",
                    "No operator action required.",
                )

            labels = ", ".join(
                str(interface.get("label") or interface.get("name") or "primary interface")
                for interface in primary
            )
            return HealthResult(
                HealthState.DEGRADED,
                "Primary network link down",
                f"Primary interface is not up: {labels}.",
                "Check the physical link, switch port, and TrueNAS network configuration.",
            )

        if any(interface.get("link_up") for interface in interfaces):
            return HealthResult(
                HealthState.ATTENTION,
                "Network path ambiguous",
                "At least one interface is up, but no primary interface is identified.",
                "Verify routing and primary-interface detection.",
            )

        return HealthResult(
            HealthState.DEGRADED,
            "Network links down",
            "No discovered network interface currently reports an active link.",
            "Check physical network connectivity and interface configuration.",
        )

    @staticmethod
    def _front_panel(lcd: dict[str, Any]) -> HealthResult:
        if not lcd.get("available"):
            return HealthResult(
                HealthState.UNKNOWN,
                "Front panel unavailable",
                "No trustworthy LCD reader or display status is currently available.",
                "Verify the front-panel serial service and hardware capability.",
            )

        if lcd.get("stale"):
            return HealthResult(
                HealthState.ATTENTION,
                "Front panel telemetry stale",
                "Front-panel status exists but is stale.",
                "Verify the LCD runtime and status bridges are updating.",
            )

        reader = lcd.get("reader")
        if isinstance(reader, dict):
            if reader.get("healthy") is False or reader.get("connected") is False:
                return HealthResult(
                    HealthState.DEGRADED,
                    "Front panel degraded",
                    str(reader.get("connection_error") or reader.get("last_reader_error") or "The LCD reader is not healthy and connected."),
                    "Inspect the LCD serial connection and TruePanel reader service.",
                )

        return HealthResult(
            HealthState.NOMINAL,
            "Front panel nominal",
            "Front-panel telemetry is current and the reader is healthy.",
            "No operator action required.",
        )

    @staticmethod
    def _services(capabilities: dict[str, Any]) -> HealthResult:
        # Mission Control does not yet expose an independent service-health
        # contract. Keep this explicit rather than inferring health from
        # capability flags that answer a different question.
        return HealthResult(
            HealthState.UNKNOWN,
            "Service health not yet surfaced",
            "Current capabilities describe features and safety boundaries, not runtime service health.",
            "No action required; service-health telemetry can be added as a dedicated source later.",
        )
