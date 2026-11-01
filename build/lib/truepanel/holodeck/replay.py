"""Black Box recordings projected through the HoloDeck host contract."""

from __future__ import annotations

import copy
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from truepanel.history.black_box import (
    BlackBoxFrame,
    BlackBoxRecorder,
    BlackBoxReplay,
    BlackBoxReplayCursor,
)

from .catalog import host_fixture
from .clock import DeterministicClock
from .provider import HoloDeckHardwareBoundary


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


_TELEMETRY_FIELDS = frozenset(
    {
        "cpu_percent",
        "ram_percent",
        "uptime_seconds",
        "load_average",
        "cpu_temperature_c",
        "sensors",
        "telemetry_fresh",
        "network",
        "network_interfaces",
        "interfaces",
        "ip_addresses",
        "platform",
        "machine",
    }
)


class BlackBoxHoloDeckProvider:
    """Expose an immutable Black Box replay as Mission Control host state."""

    name = "holodeck-black-box"
    simulation = True

    def __init__(
        self,
        replay: BlackBoxReplay,
        *,
        host: str = "battlestation",
        clock: DeterministicClock | None = None,
    ):
        if not isinstance(replay, BlackBoxReplay):
            raise TypeError("replay must be a BlackBoxReplay")
        if not replay.frames:
            raise ValueError("HoloDeck requires at least one Black Box frame")
        self.replay = replay
        self.cursor: BlackBoxReplayCursor = replay.cursor()
        self.clock = clock or DeterministicClock(replay.frames[0].captured_at)
        if self.clock() < replay.frames[0].captured_at:
            self.clock.set(replay.frames[0].captured_at)
        self.hardware = HoloDeckHardwareBoundary()
        self._baseline = copy.deepcopy(host_fixture(host))

    @classmethod
    def from_recording(
        cls,
        path: str | Path,
        **kwargs,
    ) -> BlackBoxHoloDeckProvider:
        return cls(BlackBoxRecorder(path).load_replay(), **kwargs)

    @property
    def frame(self) -> BlackBoxFrame:
        return self.cursor.current

    def update(self) -> dict[str, Any]:
        return self._project(self.frame)

    snapshot = update

    def step(self, count: int = 1) -> dict[str, Any]:
        frame = self.cursor.step(count)
        self.clock.set(max(self.clock(), frame.captured_at))
        return self._project(frame)

    def seek_sequence(self, sequence: int) -> dict[str, Any] | None:
        frame = self.cursor.seek_sequence(sequence)
        if frame is None:
            return None
        self.clock.set(max(self.clock(), frame.captured_at))
        return self._project(frame)

    def _project(self, frame: BlackBoxFrame) -> dict[str, Any]:
        state = copy.deepcopy(self._baseline)
        telemetry = _mapping(frame.telemetry)
        for key in _TELEMETRY_FIELDS:
            if key in telemetry:
                state[key] = copy.deepcopy(telemetry[key])

        fan = _mapping(frame.fan)
        if fan:
            state["fans"] = self._fan_state(state["fans"], fan)

        storage = _mapping(frame.storage)
        self._apply_storage(state, storage)

        state["lcd"].update(_mapping(frame.lcd))
        state["alerts"] = copy.deepcopy(frame.alerts)
        state["mission_control"] = copy.deepcopy(frame.mission_control)
        state["buttons"] = copy.deepcopy(frame.buttons)
        state["black_box"] = {
            "schema_version": frame.schema_version,
            "sequence": frame.sequence,
            "captured_at": frame.captured_at,
            "privacy": frame.privacy,
        }
        state["simulation"] = True
        state["read_only"] = True
        state["last_updated"] = frame.captured_at
        return state

    @staticmethod
    def _fan_state(
        baseline: Mapping[str, Any],
        recorded: Mapping[str, Any],
    ) -> dict[str, Any]:
        result = copy.deepcopy(dict(baseline))
        channels = recorded.get("fan_channels") or recorded.get("channels")
        if isinstance(channels, list):
            result["fan_channels"] = copy.deepcopy(channels)
        elif "rpm" in recorded:
            values = recorded["rpm"]
            if not isinstance(values, (list, tuple)):
                values = [values]
            for index, rpm in enumerate(values):
                if index >= len(result["fan_channels"]):
                    break
                result["fan_channels"][index]["rpm"] = int(rpm or 0)
        for key, value in recorded.items():
            if key not in {"rpm", "fan_channels", "channels"}:
                result[key] = copy.deepcopy(value)
        return result

    @staticmethod
    def _apply_storage(state: dict[str, Any], recorded: Mapping[str, Any]) -> None:
        pools = recorded.get("pools")
        if isinstance(pools, list):
            state["pools"] = copy.deepcopy(pools)
        health = recorded.get("pool_health", recorded.get("health"))
        if health is not None and state.get("pools"):
            state["pools"][0]["health"] = str(health).upper()
        temperatures = recorded.get("temperatures") or recorded.get("temps")
        if isinstance(temperatures, list):
            state["temps"] = copy.deepcopy(temperatures)


__all__ = ["BlackBoxHoloDeckProvider"]
