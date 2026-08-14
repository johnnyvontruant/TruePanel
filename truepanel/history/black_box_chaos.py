"""Simulation-only fault injection for TruePanel Black Box replays."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from truepanel.history.black_box import BlackBoxFrame, sanitize_black_box_value


SUPPORTED_CHAOS_FAULTS = frozenset(
    {
        "fan_stall",
        "storage_degraded",
        "lcd_stale",
        "mission_control_unavailable",
    }
)


@dataclass(frozen=True)
class BlackBoxChaosFault:
    """One bounded, data-only fault to overlay on a recorded frame."""

    kind: str
    details: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        if self.kind not in SUPPORTED_CHAOS_FAULTS:
            raise ValueError(f"unsupported Black Box chaos fault: {self.kind}")


def _fault_alert(kind: str, details: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "source": "black-box-chaos",
        "severity": "warning",
        "kind": kind,
        "simulated": True,
        "details": dict(details),
    }


def inject_chaos_fault(
    frame: BlackBoxFrame,
    fault: BlackBoxChaosFault,
) -> BlackBoxFrame:
    """Return a new frame with one deterministic simulation-only fault.

    This function only transforms already-sanitized Black Box data. It has no
    access to serial devices, command sockets, systemd, sysfs, or live runtime
    providers, so injected failures cannot actuate or reconfigure hardware.
    """

    if not isinstance(frame, BlackBoxFrame):
        raise TypeError("frame must be a BlackBoxFrame")
    if not isinstance(fault, BlackBoxChaosFault):
        raise TypeError("fault must be a BlackBoxChaosFault")

    details = sanitize_black_box_value(dict(fault.details or {}))

    telemetry = dict(frame.telemetry)
    lcd = dict(frame.lcd)
    fan = dict(frame.fan)
    storage = dict(frame.storage)
    alerts = [dict(item) for item in frame.alerts]
    buttons = dict(frame.buttons)
    mission_control = dict(frame.mission_control)

    if fault.kind == "fan_stall":
        fan.update(
            {
                "healthy": False,
                "rpm": 0,
                "simulated_fault": "fan_stall",
            }
        )
    elif fault.kind == "storage_degraded":
        storage.update(
            {
                "health": "DEGRADED",
                "simulated_fault": "storage_degraded",
            }
        )
    elif fault.kind == "lcd_stale":
        lcd.update(
            {
                "stale": True,
                "simulated_fault": "lcd_stale",
            }
        )
    elif fault.kind == "mission_control_unavailable":
        mission_control.update(
            {
                "available": False,
                "simulated_fault": "mission_control_unavailable",
            }
        )

    alerts.append(_fault_alert(fault.kind, details))

    return BlackBoxFrame.capture(
        captured_at=frame.captured_at,
        sequence=frame.sequence,
        telemetry=telemetry,
        lcd=lcd,
        fan=fan,
        storage=storage,
        alerts=alerts,
        buttons=buttons,
        mission_control=mission_control,
    )


class BlackBoxChaosScenario:
    """Apply deterministic fault overlays to selected replay sequences."""

    def __init__(
        self,
        faults_by_sequence: Mapping[int, BlackBoxChaosFault],
    ):
        normalized: dict[int, BlackBoxChaosFault] = {}
        for sequence, fault in faults_by_sequence.items():
            sequence_number = int(sequence)
            if sequence_number < 0:
                raise ValueError("chaos sequence must be non-negative")
            if not isinstance(fault, BlackBoxChaosFault):
                raise TypeError("scenario faults must be BlackBoxChaosFault values")
            normalized[sequence_number] = fault
        self._faults_by_sequence = normalized

    def apply(self, frame: BlackBoxFrame) -> BlackBoxFrame:
        """Project a frame through the scenario without mutating the input."""

        if not isinstance(frame, BlackBoxFrame):
            raise TypeError("frame must be a BlackBoxFrame")

        fault = self._faults_by_sequence.get(frame.sequence)
        if fault is None:
            return frame
        return inject_chaos_fault(frame, fault)
