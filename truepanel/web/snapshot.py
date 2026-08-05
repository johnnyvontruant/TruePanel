"""Read-only data services for TruePanel Mission Control."""

from __future__ import annotations

import json
import platform
import socket
import time
from pathlib import Path
from typing import Any

from collector import TruePanelCollector
from truepanel.config.loader import load_config
from truepanel.hardware.fans import (
    get_status as get_fan_status,
)
from truepanel.history.fan_control import (
    DEFAULT_FAN_CONTROL_HISTORY_PATH,
    FanControlHistory,
)
from truepanel.history.thermal_observer import (
    DEFAULT_THERMAL_OBSERVER_HISTORY_PATH,
    ThermalObserverHistory,
)
from truepanel.history.thermal_commissioning import (
    DEFAULT_THERMAL_COMMISSIONING_HISTORY_PATH,
    ThermalCommissioningHistory,
)
from truepanel.hardware.fan_status_bridge import (
    DEFAULT_FAN_CONTROL_STATUS_PATH,
    FanControlStatusBridge,
)
from truepanel.hardware.lcd_reader_status_bridge import (
    DEFAULT_LCD_READER_STATUS_PATH,
    LCDReaderStatusBridge,
)
from truepanel.hardware.lcd_display_status_bridge import (
    DEFAULT_LCD_DISPLAY_STATUS_PATH,
    LCDDisplayStatusBridge,
)
from truepanel.hardware.thermal_commissioning import (
    thermal_commissioning_state,
)


DEFAULT_HISTORY_PATH = Path(
    "/var/lib/truepanel/history/telemetry.jsonl"
)


def _safe_number(
    value: Any,
    default: float = 0.0,
) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _safe_list(value: Any) -> list:
    if isinstance(value, list):
        return value

    if isinstance(value, tuple):
        return list(value)

    return []


class SnapshotService:
    """Build JSON-safe read-only dashboard payloads."""

    def __init__(
        self,
        collector=None,
        config=None,
        history_path=None,
        fan_control_status_path=None,
        lcd_reader_status_path=None,
        lcd_display_status_path=None,
        fan_control_history_path=None,
        thermal_observer_history_path=None,
        thermal_commissioning_history_path=None,
        clock=None,
    ):
        self.collector = (
            collector
            or TruePanelCollector()
        )

        self.config = (
            config
            or load_config()
        )

        self.clock = (
            clock
            or time.time
        )

        self.fan_control_bridge = (
            FanControlStatusBridge(
                fan_control_status_path
                or DEFAULT_FAN_CONTROL_STATUS_PATH,
                clock=self.clock,
            )
        )

        self.lcd_reader_bridge = (
            LCDReaderStatusBridge(
                lcd_reader_status_path
                or DEFAULT_LCD_READER_STATUS_PATH,
                clock=self.clock,
            )
        )

        self.lcd_display_bridge = (
            LCDDisplayStatusBridge(
                lcd_display_status_path
                or DEFAULT_LCD_DISPLAY_STATUS_PATH,
                clock=self.clock,
            )
        )

        history_config = self.config.get(
            "history",
            {},
        )

        configured_path = history_config.get(
            "path",
            DEFAULT_HISTORY_PATH,
        )

        self.history_path = Path(
            history_path
            or configured_path
        )

        self.fan_control_history = FanControlHistory(
            fan_control_history_path
            or history_config.get(
                "fan_control_path",
                DEFAULT_FAN_CONTROL_HISTORY_PATH,
            ),
            enabled=True,
            clock=self.clock,
        )

        self.thermal_observer_history = (
            ThermalObserverHistory(
                thermal_observer_history_path
                or history_config.get(
                    "thermal_observer_path",
                    (
                        DEFAULT_THERMAL_OBSERVER_HISTORY_PATH
                    ),
                ),
                enabled=True,
                clock=self.clock,
            )
        )

        self.thermal_commissioning_history = (
            ThermalCommissioningHistory(
                thermal_commissioning_history_path
                or history_config.get(
                    "thermal_commissioning_path",
                    (
                        DEFAULT_THERMAL_COMMISSIONING_HISTORY_PATH
                    ),
                ),
                enabled=True,
                clock=self.clock,
            )
        )

    def status(self) -> dict[str, Any]:
        state = dict(
            self.collector.update()
            or {}
        )

        return {
            "schema_version": 1,
            "read_only": True,
            "timestamp": self.clock(),
            "system": self._system_payload(
                state
            ),
            "storage": self._storage_payload(
                state
            ),
            "network": self._network_payload(
                state
            ),
            "lcd": self._lcd_payload(),
            "fans": self._fan_payload(),
            "capabilities": (
                self.capabilities()
            ),
        }

    def lcd_status(self) -> dict[str, Any]:
        """
        Return lightweight LCD state without refreshing system telemetry.
        """

        return {
            "schema_version": 1,
            "read_only": True,
            "timestamp": self.clock(),
            "lcd": self._lcd_payload(),
        }


    def _lcd_payload(self) -> dict[str, Any]:
        reader_status = (
            self.lcd_reader_bridge.read(
                max_age=30.0
            )
        )
        display_status = (
            self.lcd_display_bridge.read(
                max_age=15.0
            )
        )

        default_reader = {
            "thread_alive": False,
            "dispatcher_alive": False,
            "stop_requested": False,
            "dispatcher_started_at": None,
            "dispatcher_stopped_at": None,
            "dispatcher_events": 0,
            "dispatch_queue_depth": 0,
            "replies": 0,
            "reader_errors": 0,
            "last_reader_error": None,
            "button_reports": 0,
            "last_button_mask": 0,
            "last_pressed_button_mask": 0,
            "last_button_time": None,
            "callback_count": 0,
            "callback_errors": 0,
            "last_callback_error": None,
            "last_callback_duration_ms": None,
            "max_callback_duration_ms": None,
            "queued_button_events": 0,
        }

        display_payload = None

        if display_status is not None:
            display = display_status[
                "display"
            ]

            display_payload = {
                "line1": display[
                    "line1"
                ],
                "line2": display[
                    "line2"
                ],
                "page": display.get(
                    "page"
                ),
                "source": display.get(
                    "source",
                    "runtime",
                ),
                "timestamp": display_status[
                    "timestamp"
                ],
                "age_seconds": display_status[
                    "age_seconds"
                ],
                "stale": display_status[
                    "stale"
                ],
            }

        if reader_status is None:
            reader = default_reader
            reader_timestamp = None
            reader_age = None
            reader_stale = True
        else:
            reader = reader_status[
                "reader"
            ]
            reader_timestamp = reader_status[
                "timestamp"
            ]
            reader_age = reader_status[
                "age_seconds"
            ]
            reader_stale = (
                float(
                    reader_status.get(
                        "age_seconds",
                        0.0,
                    )
                )
                > 30.0
            )

        component_staleness = []

        if reader_status is not None:
            component_staleness.append(
                bool(reader_stale)
            )

        if display_status is not None:
            component_staleness.append(
                bool(
                    display_status[
                        "stale"
                    ]
                )
            )

        return {
            "available": bool(
                reader_status is not None
                or display_status is not None
            ),
            "stale": (
                all(component_staleness)
                if component_staleness
                else True
            ),
            "timestamp": reader_timestamp,
            "age_seconds": reader_age,
            "reader": reader,
            "display": display_payload,
        }


    def fan_control_history_payload(
        self,
        limit: int = 20,
    ) -> dict[str, Any]:
        limit = max(
            1,
            min(
                int(limit),
                200,
            ),
        )

        events = self.fan_control_history.read(
            limit=limit
        )

        return {
            "schema_version": 1,
            "read_only": True,
            "path": str(
                self.fan_control_history.path
            ),
            "count": len(events),
            "events": events,
        }

    def thermal_observer_history_payload(
        self,
        limit: int = 20,
    ) -> dict[str, Any]:
        limit = max(
            1,
            min(
                int(limit),
                200,
            ),
        )

        events = (
            self.thermal_observer_history
            .read(
                limit=limit
            )
        )

        return {
            "schema_version": 1,
            "read_only": True,
            "policy_mode": "observe_only",
            "path": str(
                self.thermal_observer_history.path
            ),
            "count": len(events),
            "events": events,
        }

    def thermal_commissioning_history_payload(
        self,
        limit: int = 20,
    ) -> dict[str, Any]:
        limit = max(
            1,
            min(
                int(limit),
                200,
            ),
        )

        events = (
            self.thermal_commissioning_history
            .read(
                limit=limit
            )
        )

        return {
            "schema_version": 1,
            "read_only": True,
            "path": str(
                self.thermal_commissioning_history.path
            ),
            "count": len(events),
            "events": events,
        }

    def capabilities(self) -> dict[str, Any]:
        hardware = self.config.get(
            "hardware",
            {},
        )

        night_mode = self.config.get(
            "night_mode",
            {},
        )

        return {
            "dashboard": {
                "status": True,
                "history": True,
                "live_refresh": True,
            },
            "configuration": {
                "available": False,
                "planned": True,
                "night_mode_configured": bool(
                    night_mode
                ),
            },
            "hardware_controls": {
                "available": False,
                "planned": True,
                "fan_telemetry": True,
                "fan_control": bool(
                    hardware.get(
                        "fan_control",
                        {},
                    ).get(
                        "enabled",
                        False,
                    )
                ),
                "bay_leds": bool(
                    hardware.get(
                        "bay_leds"
                    )
                ),
                "buzzer": bool(
                    self.config.get(
                        "buzzer"
                    )
                ),
            },
            "safety": {
                "read_only": True,
                "remote_writes_enabled": (
                    False
                ),
                "direct_device_access": (
                    False
                ),
            },
        }

    def history(
        self,
        limit: int = 240,
    ) -> dict[str, Any]:
        limit = max(
            1,
            min(
                int(limit),
                2000,
            ),
        )

        samples = []

        try:
            with self.history_path.open(
                "r",
                encoding="utf-8",
            ) as handle:
                for raw_line in handle:
                    line = raw_line.strip()

                    if not line:
                        continue

                    try:
                        payload = json.loads(
                            line
                        )
                    except json.JSONDecodeError:
                        continue

                    if isinstance(
                        payload,
                        dict,
                    ):
                        samples.append(
                            payload
                        )
        except FileNotFoundError:
            samples = []
        except OSError:
            samples = []

        samples = samples[-limit:]

        return {
            "schema_version": 1,
            "read_only": True,
            "path": str(
                self.history_path
            ),
            "count": len(samples),
            "samples": samples,
        }

    @staticmethod
    def _system_payload(
        state: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "hostname": (
                socket.gethostname()
            ),
            "platform": (
                platform.system()
            ),
            "machine": (
                platform.machine()
            ),
            "cpu_percent": _safe_number(
                state.get(
                    "cpu_percent"
                )
            ),
            "ram_percent": _safe_number(
                state.get(
                    "ram_percent"
                )
            ),
            "uptime_seconds": _safe_number(
                state.get(
                    "uptime_seconds"
                )
            ),
            "load_average": _safe_list(
                state.get(
                    "load_average"
                )
            ),
        }

    @staticmethod
    def _storage_payload(
        state: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "pools": _safe_list(
                state.get(
                    "pools"
                )
            ),
            "temperatures": _safe_list(
                state.get(
                    "temps"
                )
            ),
            "alerts": _safe_list(
                state.get(
                    "alerts"
                )
            ),
        }

    @staticmethod
    def _network_payload(
        state: dict[str, Any],
    ) -> list[dict[str, Any]]:
        candidates = (
            state.get(
                "network_interfaces"
            )
            or state.get(
                "interfaces"
            )
            or state.get(
                "ip_addresses"
            )
            or []
        )

        if isinstance(
            candidates,
            dict,
        ):
            return [
                {
                    "name": str(name),
                    "address": value,
                }
                for name, value
                in candidates.items()
            ]

        if isinstance(
            candidates,
            list,
        ):
            return candidates

        return []

    def _fan_payload(self) -> dict[str, Any]:
        try:
            payload = dict(
                get_fan_status()
                or {}
            )
        except Exception:
            payload = {}

        hardware_config = self.config.get(
            "hardware",
            {},
        )
        fan_config = hardware_config.get(
            "fans",
            {},
        )
        configured_channels = fan_config.get(
            "channels",
            {},
        )

        if not isinstance(
            configured_channels,
            dict,
        ):
            configured_channels = {}

        channels = []

        for channel in (
            payload.get(
                "fan_channels",
                [],
            )
            or []
        ):
            if not isinstance(
                channel,
                dict,
            ):
                continue

            try:
                number = int(
                    channel.get(
                        "number",
                        0,
                    )
                    or 0
                )
            except (
                TypeError,
                ValueError,
            ):
                continue

            if number <= 0:
                continue

            alarm = channel.get(
                "alarm"
            )

            channel_config = (
                configured_channels.get(
                    number,
                )
                or configured_channels.get(
                    str(number),
                )
                or {}
            )

            if not isinstance(
                channel_config,
                dict,
            ):
                channel_config = {}

            label = str(
                channel_config.get(
                    "label",
                    f"Fan {number}",
                )
            )

            monitored = bool(
                channel_config.get(
                    "monitored",
                    False,
                )
            )

            channels.append(
                {
                    "number": number,
                    "label": label,
                    "monitored": monitored,
                    "rpm": int(
                        channel.get(
                            "rpm",
                            0,
                        )
                        or 0
                    ),
                    "alarm": (
                        bool(alarm)
                        if alarm is not None
                        else None
                    ),
                    "pwm": int(
                        channel.get(
                            "pwm",
                            0,
                        )
                        or 0
                    ),
                    "pwm_mode": str(
                        channel.get(
                            "pwm_mode",
                            "Unavailable",
                        )
                    ),
                }
            )

        return {
            "available": bool(
                payload.get(
                    "available",
                    payload,
                )
            ),
            "fan1_rpm": int(
                payload.get(
                    "fan1_rpm",
                    0,
                )
                or 0
            ),
            "fan2_rpm": int(
                payload.get(
                    "fan2_rpm",
                    0,
                )
                or 0
            ),
            "pwm1": int(
                payload.get(
                    "pwm1",
                    0,
                )
                or 0
            ),
            "pwm2": int(
                payload.get(
                    "pwm2",
                    0,
                )
                or 0
            ),
            "pwm1_mode": str(
                payload.get(
                    "pwm1_mode",
                    "Unavailable",
                )
            ),
            "pwm2_mode": str(
                payload.get(
                    "pwm2_mode",
                    "Unavailable",
                )
            ),
            "channels": channels,
            "control": self._fan_control_payload(
                controller_available=bool(
                    payload.get(
                        "available",
                        payload,
                    )
                )
            ),
        }

    def _fan_control_payload(
        self,
        *,
        controller_available: bool,
    ) -> dict[str, Any]:
        hardware_config = self.config.get(
            "hardware",
            {},
        )

        control_config = hardware_config.get(
            "fan_control",
            {},
        )

        if not isinstance(
            control_config,
            dict,
        ):
            control_config = {}

        enabled = bool(
            control_config.get(
                "enabled",
                False,
            )
        )

        try:
            command_timeout = max(
                0,
                int(
                    control_config.get(
                        "command_timeout",
                        300,
                    )
                ),
            )
        except (
            TypeError,
            ValueError,
        ):
            command_timeout = 300

        raw_channels = control_config.get(
            "controlled_channels",
            [
                1,
                2,
            ],
        )

        if not isinstance(
            raw_channels,
            (
                list,
                tuple,
            ),
        ):
            raw_channels = [
                1,
                2,
            ]

        controlled_channels = []

        for channel in raw_channels:
            try:
                number = int(
                    channel
                )
            except (
                TypeError,
                ValueError,
            ):
                continue

            if (
                number in (
                    1,
                    2,
                )
                and number
                not in controlled_channels
            ):
                controlled_channels.append(
                    number
                )

        if not controlled_channels:
            controlled_channels = [
                1,
                2,
            ]

        runtime_status = (
            self.fan_control_bridge.read(
                max_age=30.0,
            )
        )

        if runtime_status is not None:
            return {
                "configured": bool(
                    control_config
                ),
                "enabled": bool(
                    runtime_status[
                        "enabled"
                    ]
                ),
                "available": bool(
                    controller_available
                ),
                "connected": bool(
                    runtime_status[
                        "connected"
                    ]
                ),
                "active_profile": (
                    runtime_status[
                        "active_profile"
                    ]
                ),
                "requested_profile": (
                    runtime_status[
                        "requested_profile"
                    ]
                ),
                "command_timeout": (
                    command_timeout
                ),
                "controlled_channels": (
                    controlled_channels
                ),
                "remaining_seconds": (
                    runtime_status[
                        "remaining_seconds"
                    ]
                ),
                "last_reason": (
                    runtime_status[
                        "last_reason"
                    ]
                ),
                "control_authority": (
                    runtime_status.get(
                        "control_authority",
                        "automatic",
                    )
                ),
                "safety_hold": bool(
                    runtime_status.get(
                        "safety_hold",
                        False,
                    )
                ),
                "recovery_pending": bool(
                    runtime_status.get(
                        "recovery_pending",
                        False,
                    )
                ),
                "recovery_healthy_cycles": int(
                    runtime_status.get(
                        "recovery_healthy_cycles",
                        0,
                    )
                    or 0
                ),
                "recovery_required_cycles": int(
                    runtime_status.get(
                        "recovery_required_cycles",
                        3,
                    )
                    or 3
                ),
                "status_age_seconds": (
                    runtime_status[
                        "age_seconds"
                    ]
                ),
                "thermal_policy_mode": (
                    runtime_status.get(
                        "thermal_policy_mode",
                        "observe_only",
                    )
                ),
                "thermal_operator_armed": bool(
                    runtime_status.get(
                        "thermal_operator_armed",
                        False,
                    )
                ),
                "thermal_dry_run": bool(
                    runtime_status.get(
                        "thermal_dry_run",
                        True,
                    )
                ),
                "thermal_control_state": (
                    runtime_status.get(
                        "thermal_control_state",
                        "awaiting_evaluation",
                    )
                ),
                "thermal_control_reason": (
                    runtime_status.get(
                        "thermal_control_reason",
                        (
                            "Thermal control status "
                            "is unavailable."
                        ),
                    )
                ),
                "thermal_simulated_profile": (
                    runtime_status.get(
                        "thermal_simulated_profile",
                        "automatic",
                    )
                ),
                "thermal_control_cooldown_remaining": (
                    runtime_status.get(
                        "thermal_control_cooldown_remaining",
                        0.0,
                    )
                ),
                "thermal_supervised_session_active": bool(
                    runtime_status.get(
                        "thermal_supervised_session_active",
                        False,
                    )
                ),
                "thermal_supervised_session_remaining": (
                    runtime_status.get(
                        "thermal_supervised_session_remaining",
                        0.0,
                    )
                ),
                "thermal_automatic_lease_active": bool(
                    runtime_status.get(
                        "thermal_automatic_lease_active",
                        False,
                    )
                ),
                "thermal_automatic_lease_remaining": (
                    runtime_status.get(
                        "thermal_automatic_lease_remaining",
                        0.0,
                    )
                ),
                "thermal_automatic_lease_seconds": (
                    runtime_status.get(
                        "thermal_automatic_lease_seconds",
                        600.0,
                    )
                ),
                "thermal_automatic_allowed_profiles": (
                    runtime_status.get(
                        "thermal_automatic_allowed_profiles",
                        [
                            "balanced",
                            "cooling_boost",
                        ],
                    )
                ),
                "thermal_safety_fingerprint": (
                    runtime_status.get(
                        "thermal_safety_fingerprint",
                        "",
                    )
                ),
                "thermal_commissioned_fingerprint": (
                    runtime_status.get(
                        "thermal_commissioned_fingerprint",
                        "",
                    )
                ),
                "thermal_commissioned_fingerprint_match": bool(
                    runtime_status.get(
                        "thermal_commissioned_fingerprint_match",
                        False,
                    )
                ),
                "thermal_commissioning_state": (
                    thermal_commissioning_state(
                        policy_mode=runtime_status.get(
                            "thermal_policy_mode",
                            "observe_only",
                        ),
                        operator_armed=runtime_status.get(
                            "thermal_operator_armed",
                            False,
                        ),
                        dry_run=runtime_status.get(
                            "thermal_dry_run",
                            True,
                        ),
                        supervised_session_active=(
                            runtime_status.get(
                                "thermal_supervised_session_active",
                                False,
                            )
                        ),
                    )
                ),
                "thermal_recommended_profile": (
                    runtime_status.get(
                        "thermal_recommended_profile",
                        "automatic",
                    )
                ),
                "thermal_hottest_temperature_c": (
                    runtime_status.get(
                        "thermal_hottest_temperature_c"
                    )
                ),
                "thermal_recommendation_reason": (
                    runtime_status.get(
                        "thermal_recommendation_reason",
                        (
                            "Thermal recommendation "
                            "unavailable."
                        ),
                    )
                ),
                "thermal_recommendation_changed": bool(
                    runtime_status.get(
                        "thermal_recommendation_changed",
                        False,
                    )
                ),
                "thermal_telemetry_valid": bool(
                    runtime_status.get(
                        "thermal_telemetry_valid",
                        False,
                    )
                ),
                "thermal_profile_alignment": (
                    runtime_status.get(
                        "thermal_profile_alignment",
                        "telemetry_unavailable",
                    )
                ),
                "thermal_control_readiness": (
                    runtime_status.get(
                        "thermal_control_readiness",
                        {
                            "ready": False,
                            "armed": False,
                            "state": "blocked",
                            "checks": {},
                            "blocking_reasons": [
                                (
                                    "Thermal readiness "
                                    "status is unavailable."
                                )
                            ],
                        },
                    )
                ),
            }

        if not enabled:
            reason = (
                "Fan control is disabled."
            )
        elif not controller_available:
            reason = (
                "Fintek fan controller is unavailable."
            )
        else:
            reason = (
                "Fan-control runtime status is unavailable."
            )

        return {
            "configured": bool(
                control_config
            ),
            "enabled": enabled,
            "available": bool(
                controller_available
            ),
            "connected": False,
            "active_profile": (
                "automatic"
            ),
            "requested_profile": (
                "automatic"
            ),
            "command_timeout": (
                command_timeout
            ),
            "controlled_channels": (
                controlled_channels
            ),
            "remaining_seconds": None,
            "last_reason": reason,
            "control_authority": "automatic",
            "safety_hold": False,
            "recovery_pending": False,
            "recovery_healthy_cycles": 0,
            "recovery_required_cycles": int(
                control_config.get(
                    "safety_recovery_cycles",
                    3,
                )
                or 3
            ),
            "thermal_policy_mode": "observe_only",
            "thermal_operator_armed": False,
            "thermal_dry_run": True,
            "thermal_control_state": "blocked",
            "thermal_control_reason": (
                "Thermal control is unavailable."
            ),
            "thermal_simulated_profile": "automatic",
            "thermal_control_cooldown_remaining": 0.0,
            "thermal_supervised_session_active": False,
            "thermal_supervised_session_remaining": 0.0,
            "thermal_commissioning_state": (
                thermal_commissioning_state(
                    policy_mode="observe_only",
                    operator_armed=False,
                    dry_run=True,
                    supervised_session_active=False,
                )
            ),
            "thermal_recommended_profile": "automatic",
            "thermal_hottest_temperature_c": None,
            "thermal_recommendation_reason": (
                "Thermal observer status is unavailable."
            ),
            "thermal_recommendation_changed": False,
            "thermal_telemetry_valid": False,
            "thermal_profile_alignment": (
                "telemetry_unavailable"
            ),
            "thermal_control_readiness": {
                "ready": False,
                "armed": False,
                "state": "blocked",
                "checks": {
                    "policy_allows_automatic": False,
                    "controller_connected": False,
                    "telemetry_valid": False,
                    "safety_clear": True,
                    "recovery_clear": True,
                    "recommendation_available": False,
                    "operator_armed": False,
                },
                "blocking_reasons": [
                    (
                        "Thermal policy is not configured "
                        "for automatic control."
                    ),
                    (
                        "Fan-control runtime is not "
                        "connected."
                    ),
                    (
                        "Thermal telemetry is unavailable."
                    ),
                    (
                        "Thermal recommendation is "
                        "unavailable."
                    ),
                    (
                        "Automatic thermal control has not "
                        "been armed by the operator."
                    ),
                ],
            },
        }
