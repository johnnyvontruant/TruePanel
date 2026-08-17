"""Whole-stack, provider-injected HoloDeck scenario execution."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from truepanel.hardware.thermal_fan_policy import (
    ThermalFanPolicy,
    ThermalFanRecommendation,
)
from truepanel.mission_control.event import MissionEvent
from truepanel.mission_control.watchers.fan_health import FanHealthWatcher
from truepanel.watchers.storage_health import StorageHealthWatcher
from truepanel.web.snapshot import SnapshotService

from .provider import HoloDeckHostProvider


@dataclass(frozen=True)
class HoloDeckObservation:
    """One deterministic whole-stack observation."""

    state: dict[str, Any]
    recommendation: ThermalFanRecommendation
    events: tuple[MissionEvent, ...]
    snapshot: dict[str, Any]


class _SimulatedServices:
    def snapshot(self) -> dict[str, Any]:
        return {
            "available": True,
            "services": [
                {
                    "name": "holodeck.service",
                    "required": True,
                    "observed": True,
                    "load_state": "loaded",
                    "active_state": "active",
                    "sub_state": "running",
                }
            ],
        }


class HoloDeckScenarioRunner:
    """Drive real policy, watchers, SnapshotService, and Health Intelligence.

    Every provider and runtime bridge is explicitly injected.  The runner
    never constructs a production hardware manager and never reads a
    production ``/run`` or ``/var`` status path.
    """

    def __init__(
        self,
        provider: HoloDeckHostProvider,
        *,
        runtime_dir: str | Path,
        config: dict[str, Any] | None = None,
    ) -> None:
        if not provider.simulation:
            raise ValueError("HoloDeckScenarioRunner requires a simulation provider")

        self.provider = provider
        self.runtime_dir = Path(runtime_dir)
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        self.config = config or {
            "hardware": {
                "fans": {
                    "channels": {
                        "1": {"label": "Rear Fan 1", "monitored": True},
                        "2": {"label": "Rear Fan 2", "monitored": True},
                        "3": {"label": "PCIe Fan", "monitored": False},
                    }
                }
            }
        }

        self.policy = ThermalFanPolicy(
            minimum_dwell_seconds=0,
            clock=provider.clock,
        )
        fan_channels = self.config["hardware"]["fans"]["channels"]
        self.fan_watcher = FanHealthWatcher(
            status_provider=self._fan_status,
            channels={int(key): value for key, value in fan_channels.items()},
            interval=0,
            consecutive_failures=3,
            emit_initial_conditions=False,
            clock=provider.clock,
        )
        self.storage_watcher = StorageHealthWatcher(
            report_provider=self._storage_report,
            interval=0,
            clock=provider.clock,
            emit_initial_conditions=False,
        )

        path = self.runtime_dir
        self.snapshot_service = SnapshotService(
            collector=provider,
            config=self.config,
            history_path=path / "telemetry.jsonl",
            fan_control_status_path=path / "fan-control.json",
            lcd_reader_status_path=path / "lcd-reader.json",
            lcd_display_status_path=path / "lcd-display.json",
            fan_control_history_path=path / "fan-history.jsonl",
            thermal_observer_history_path=path / "thermal-history.jsonl",
            thermal_commissioning_history_path=path / "commissioning.jsonl",
            service_status_provider=_SimulatedServices(),
            fan_status_provider=self._fan_status,
            clock=provider.clock,
        )

    def _fan_status(self) -> dict[str, Any]:
        return self.provider.update().get("fans", {})

    def _thermal_telemetry(self, state: dict[str, Any]) -> dict[str, Any]:
        sensors = state.get("sensors", {})
        temperatures = (
            tuple(sensors.values())
            if isinstance(sensors, dict)
            else ()
        )
        return {
            "temperatures_c": temperatures,
            "telemetry_fresh": bool(state.get("telemetry_fresh", False)),
        }

    def _storage_report(self) -> dict[str, Any]:
        state = self.provider.update()
        bays = state.get("enclosure", {}).get("bays", [])
        devices = []
        for bay in bays:
            if not isinstance(bay, dict) or not bay.get("present", False):
                continue
            health = str(bay.get("health", "UNKNOWN")).upper()
            if health == "ONLINE":
                device_state = "healthy"
            elif health in {"FAULTED", "UNAVAIL", "OFFLINE", "REMOVED"}:
                device_state = "critical"
            else:
                device_state = "warning"
            devices.append(
                {
                    "device": bay.get("device"),
                    "label": f"Bay {bay.get('bay', '?')}",
                    "physical_bay": bay.get("bay"),
                    "state": device_state,
                    "message": "" if device_state == "healthy" else health,
                    "source": "holodeck",
                }
            )
        return {"devices": devices}

    def _publish_lcd(self, state: dict[str, Any]) -> None:
        lcd = state.get("lcd", {})
        connected = bool(isinstance(lcd, dict) and lcd.get("connected"))
        self.snapshot_service.lcd_reader_bridge.publish(
            {
                "connected": connected,
                "thread_alive": connected,
                "dispatcher_alive": connected,
                "connection_error": None if connected else "Simulated LCD disconnect",
                "port": "virtual:a125",
                "speed": 1200,
            }
        )

    def step(self, seconds: float = 0.0) -> HoloDeckObservation:
        """Advance simulated time and evaluate one complete observation."""

        state = (
            self.provider.advance(seconds)
            if seconds
            else self.provider.update()
        )
        telemetry = self._thermal_telemetry(state)
        recommendation = self.policy.evaluate(
            telemetry["temperatures_c"],
            telemetry_fresh=telemetry["telemetry_fresh"],
        )
        self._publish_lcd(state)

        events = []
        for watcher in (self.fan_watcher, self.storage_watcher):
            event = watcher(state)
            if event is not None:
                events.append(event)

        return HoloDeckObservation(
            state=state,
            recommendation=recommendation,
            events=tuple(events),
            snapshot=self.snapshot_service.status(),
        )


__all__ = ["HoloDeckObservation", "HoloDeckScenarioRunner"]
