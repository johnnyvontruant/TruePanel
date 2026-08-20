"""Stateful fixture-backed host provider with a closed hardware boundary."""

from __future__ import annotations

import copy
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .clock import DeterministicClock
from .scenario import Scenario, ScenarioEvent


class SimulationSafetyError(RuntimeError):
    """Raised when simulated code attempts to cross into real hardware."""


class HoloDeckHardwareBoundary:
    """A deny-all actuator exposed to simulation consumers."""

    simulation = True

    def __getattr__(self, name: str):
        raise SimulationSafetyError(
            f"real hardware operation {name!r} is unavailable in HoloDeck"
        )

    def open(self, *_args, **_kwargs):
        raise SimulationSafetyError("device access is unavailable in HoloDeck")

    def write(self, *_args, **_kwargs):
        raise SimulationSafetyError("hardware writes are unavailable in HoloDeck")

    def run(self, *_args, **_kwargs):
        raise SimulationSafetyError("host commands are unavailable in HoloDeck")


class HoloDeckHostProvider:
    """Present a deterministic host using sanitized JSON fixtures."""

    name = "holodeck"
    simulation = True

    def __init__(
        self,
        fixture: Mapping[str, Any],
        *,
        scenario: Scenario | None = None,
        clock: DeterministicClock | None = None,
    ):
        self.clock = clock or DeterministicClock()
        self.hardware = HoloDeckHardwareBoundary()
        self._baseline = copy.deepcopy(dict(fixture))
        self._state = copy.deepcopy(self._baseline)
        self._events = tuple(scenario.events if scenario else ())
        self._next_event = 0
        self.applied_events: list[ScenarioEvent] = []
        self._validate_fixture()

    @classmethod
    def from_path(
        cls,
        path: str | Path,
        **kwargs,
    ) -> HoloDeckHostProvider:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(payload, **kwargs)

    def _validate_fixture(self) -> None:
        required = {"hostname", "cpu_percent", "ram_percent", "pools", "temps", "network"}
        missing = sorted(required.difference(self._state))
        if missing:
            raise ValueError(f"HoloDeck fixture missing fields: {', '.join(missing)}")
        if self._state.get("simulation") is False:
            raise ValueError("HoloDeck fixture cannot disable simulation mode")
        self._state["simulation"] = True
        self._state["read_only"] = True

    def reset(self) -> None:
        self._state = copy.deepcopy(self._baseline)
        self._state["simulation"] = True
        self._state["read_only"] = True
        self._next_event = 0
        self.applied_events.clear()
        self.clock.reset()

    def update(self) -> dict[str, Any]:
        self._apply_due_events()
        snapshot = copy.deepcopy(self._state)
        snapshot["last_updated"] = self.clock()
        return snapshot

    snapshot = update

    def advance(self, seconds: float) -> dict[str, Any]:
        self.clock.advance(seconds)
        return self.update()

    def inject(self, event_type: str, **values: Any) -> dict[str, Any]:
        event = ScenarioEvent.from_dict(
            {"at": self.clock(), "type": event_type, **values}
        )
        self._apply(event)
        self.applied_events.append(event)
        return self.update()

    def apply_fan_decision(self, decision: Any) -> None:
        """Apply an already validated decision to simulated fan state only."""

        profile = getattr(decision, "effective_profile", None)
        profile_name = getattr(profile, "value", str(profile or "automatic"))
        pwm = getattr(decision, "pwm", None)
        channels = self._state.setdefault("fans", {}).setdefault(
            "fan_channels",
            [],
        )
        for channel in channels:
            if int(channel.get("number", -1)) not in {1, 2}:
                continue
            channel["profile"] = profile_name
            if pwm is None:
                channel["pwm_mode"] = "Auto"
            else:
                channel["pwm"] = int(pwm)
                channel["pwm_mode"] = "Manual"
        self._state["fans"]["active_profile"] = profile_name

    def _apply_due_events(self) -> None:
        while self._next_event < len(self._events):
            event = self._events[self._next_event]
            if event.at > self.clock():
                break
            self._apply(event)
            self.applied_events.append(event)
            self._next_event += 1

    def _apply(self, event: ScenarioEvent) -> None:
        handlers = {
            "temperature": self._temperature,
            "fan_stall": self._fan_stall,
            "fan_recover": self._fan_recover,
            "disk_fault": self._disk_fault,
            "disk_recover": self._disk_recover,
            "disk_remove": self._disk_remove,
            "disk_insert": self._disk_insert,
            "network_down": self._network_down,
            "network_up": self._network_up,
            "lcd_disconnect": lambda _v: self._set_lcd(False),
            "lcd_connect": lambda _v: self._set_lcd(True),
            "telemetry_stale": lambda _v: self._state.__setitem__("telemetry_fresh", False),
            "telemetry_fresh": lambda _v: self._state.__setitem__("telemetry_fresh", True),
            "pool_health": self._pool_health,
        }
        handlers[event.type](event.values)

    def _temperature(self, values: Mapping[str, Any]) -> None:
        sensor = str(values.get("sensor", "cpu"))
        value = float(values["value"])
        sensors = self._state.setdefault("sensors", {})
        sensors[sensor] = value
        if sensor == "cpu":
            self._state["cpu_temperature_c"] = value

    def _fan(self, channel: int) -> dict[str, Any]:
        fans = self._state.setdefault("fans", {}).setdefault("fan_channels", [])
        for fan in fans:
            if int(fan.get("number", -1)) == channel:
                return fan
        raise ValueError(f"unknown simulated fan channel: {channel}")

    def _fan_stall(self, values: Mapping[str, Any]) -> None:
        fan = self._fan(int(values["channel"]))
        fan.update({"rpm": 0, "alarm": True, "stalled": True})

    def _fan_recover(self, values: Mapping[str, Any]) -> None:
        fan = self._fan(int(values["channel"]))
        fan.update({"rpm": int(values.get("rpm", 1450)), "alarm": False, "stalled": False})

    def _bay(self, number: int) -> dict[str, Any]:
        for bay in self._state.setdefault("enclosure", {}).setdefault("bays", []):
            if int(bay.get("bay", -1)) == number:
                return bay
        raise ValueError(f"unknown simulated drive bay: {number}")

    def _baseline_bay(self, number: int) -> dict[str, Any]:
        for bay in self._baseline.get("enclosure", {}).get("bays", []):
            if int(bay.get("bay", -1)) == number:
                return copy.deepcopy(bay)
        raise ValueError(f"unknown baseline simulated drive bay: {number}")

    def _disk_fault(self, values: Mapping[str, Any]) -> None:
        self._bay(int(values["bay"])).update({"health": "FAULTED", "faulted": True})

    def _disk_recover(self, values: Mapping[str, Any]) -> None:
        bay = self._bay(int(values["bay"]))
        bay.update({"health": "ONLINE", "faulted": False, "present": True})

    def _disk_remove(self, values: Mapping[str, Any]) -> None:
        self._bay(int(values["bay"])).update({"present": False, "device": None})

    def _disk_insert(self, values: Mapping[str, Any]) -> None:
        number = int(values["bay"])
        target = self._bay(number)
        restored = self._baseline_bay(number)
        restored.update({"present": True, "health": "ONLINE", "faulted": False})
        target.clear()
        target.update(restored)

    def _interface(self, name: str) -> dict[str, Any]:
        network = self._state.setdefault("network", {})
        if name not in network:
            raise ValueError(f"unknown simulated network interface: {name}")
        return network[name]

    def _network_down(self, values: Mapping[str, Any]) -> None:
        self._interface(str(values["interface"])).update({"link_up": False, "operstate": "DOWN"})

    def _network_up(self, values: Mapping[str, Any]) -> None:
        self._interface(str(values["interface"])).update({"link_up": True, "operstate": "UP"})

    def _set_lcd(self, connected: bool) -> None:
        self._state.setdefault("lcd", {})["connected"] = connected

    def _pool_health(self, values: Mapping[str, Any]) -> None:
        name = str(values.get("pool", "HDDs"))
        for pool in self._state.setdefault("pools", []):
            if pool.get("name") == name:
                pool["health"] = str(values["health"]).upper()
                return
        raise ValueError(f"unknown simulated pool: {name}")