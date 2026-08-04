#!/usr/bin/env python3

import json
import logging
import os
import platform
import subprocess
import signal
import threading
import time

import qnaplcd
from truepanel.hardware.lcd_reader_status_bridge import (
    LCDReaderStatusBridge,
)

from collector import TruePanelCollector
from truepanel.display.widgets import progress_bar
from truepanel.config.loader import load_config
from truepanel.flightdeck.autopilot import AutoPilot
from truepanel.hardware import Buzzer
from truepanel.history import (
    FanControlHistory,
    TelemetryRecorder,
    ThermalObserverHistory,
    event_from_decision,
    event_from_recommendation,
)
from truepanel.history.thermal_commissioning import (
    ThermalCommissioningHistory,
    commissioning_event,
)
from truepanel.mission_control import MissionControl
from truepanel.hardware.bay_led_animation import (
    build_bay_led_startup_animation,
)
from truepanel.hardware.fan_status_bridge import (
    FanControlStatusBridge,
)
from truepanel.hardware.thermal_commissioning import (
    thermal_commissioning_state,
)

from truepanel.hardware.thermal_fan_policy import (
    ThermalFanPolicy,
)
from truepanel.hardware.thermal_control import (
    ThermalControlCoordinator,
)
from truepanel.hardware.bounded_automatic import (
    AUTOMATIC_LEASE_ALLOWED_PROFILES,
    AUTOMATIC_LEASE_SECONDS,
    BoundedAutomaticLease,
    thermal_safety_fingerprint,
)
from truepanel.hardware.fan_runtime import (
    build_fan_control_runtime,
)
from truepanel.hardware.fan_command import (
    FanCommandProcessor,
    FanCommandServer,
)
from truepanel.hardware.fans import (
    get_status as get_fan_status,
)
from truepanel.mission_control.alert_manager import AlertManager
from truepanel.mission_control.display_manager import DisplayManager
from truepanel.mission_control.watchers.fan_health import (
    build_fan_health_watcher,
)
from truepanel.mission_control.watchers.healthy import healthy_watcher
from truepanel.mission_control.watchers.pool import pool_watcher
from truepanel.mission_control.watchers.smart import smart_watcher
from truepanel.mission_control.watchers.storage_health import (
    build_storage_health_watcher,
)
from truepanel.mission_control.watchers.thermal import thermal_watcher
from truepanel.mission_control.watchers.zfs import zfs_watcher
from truepanel.pages.fans import (
    fan_control_page,
    fan_pwm_page,
    fan_rpm_page,
)


LOGGER = logging.getLogger(__name__)

DISPLAY_TIMEOUT = 120
PORT = "/dev/ttyS1"
PORT_SPEED = 1200

lcd = None
lcd_reader_status_bridge = (
    LCDReaderStatusBridge()
)
lcd_timer = None
menu_item = 0

zfs_pools = []
ip_addresses = []

collector = TruePanelCollector()
mission = MissionControl()
alert_manager = AlertManager()
config = load_config()
fan_control_status_bridge = FanControlStatusBridge()
fan_control_runtime = build_fan_control_runtime(
    config
)

fan_command_server = None
storage_health_watcher = build_storage_health_watcher(config)
fan_health_watcher = build_fan_health_watcher(config)
display_manager = DisplayManager(mission, alert_manager, config=config)
autopilot = AutoPilot(display_manager, config=config)
history_recorder = TelemetryRecorder(config.get("history", {}))
fan_control_history = FanControlHistory(
    config.get(
        "history",
        {},
    ).get(
        "fan_control_path",
        (
            "/var/lib/truepanel/history/"
            "fan-control.jsonl"
        ),
    ),
    enabled=bool(
        config.get(
            "history",
            {},
        ).get(
            "enabled",
            True,
        )
    ),
)
thermal_commissioning_history = (
    ThermalCommissioningHistory(
        config.get(
            "history",
            {},
        ).get(
            "thermal_commissioning_path",
            (
                "/var/lib/truepanel/history/"
                "thermal-commissioning.jsonl"
            ),
        ),
        enabled=bool(
            config.get(
                "history",
                {},
            ).get(
                "enabled",
                True,
            )
        ),
    )
)

thermal_observer_history = ThermalObserverHistory(
    config.get(
        "history",
        {},
    ).get(
        "thermal_observer_path",
        (
            "/var/lib/truepanel/history/"
            "thermal-observer.jsonl"
        ),
    ),
    enabled=bool(
        config.get(
            "history",
            {},
        ).get(
            "enabled",
            True,
        )
    ),
)

thermal_observer_last_signature = None

buzzer = Buzzer(config.get("buzzer", {}))
bay_led_startup_animation = (
    build_bay_led_startup_animation(
        config
    )
)
shutdown_requested = False

mission.register(pool_watcher)
mission.register(thermal_watcher)
mission.register(zfs_watcher)
mission.register(smart_watcher)

if storage_health_watcher is not None:
    mission.register(storage_health_watcher)

if fan_health_watcher is not None:
    mission.register(fan_health_watcher)

mission.register(healthy_watcher)


thermal_policy_config = (
    config.get(
        "hardware",
        {},
    ).get(
        "thermal_policy",
        {},
    )
)

thermal_policy_mode = str(
    thermal_policy_config.get(
        "mode",
        "observe_only",
    )
).strip().lower()

if thermal_policy_mode not in {
    "disabled",
    "observe_only",
    "automatic_control",
}:
    LOGGER.warning(
        "Unknown thermal policy mode %r; "
        "using observe_only.",
        thermal_policy_mode,
    )
    thermal_policy_mode = "observe_only"

thermal_fan_policy = ThermalFanPolicy(
    balanced_temperature_c=float(
        thermal_policy_config.get(
            "balanced_temperature_c",
            42,
        )
    ),
    cooling_boost_temperature_c=float(
        thermal_policy_config.get(
            "cooling_boost_temperature_c",
            50,
        )
    ),
    afterburners_temperature_c=float(
        thermal_policy_config.get(
            "afterburners_temperature_c",
            60,
        )
    ),
    hysteresis_c=float(
        thermal_policy_config.get(
            "hysteresis_c",
            3,
        )
    ),
    minimum_dwell_seconds=float(
        thermal_policy_config.get(
            "minimum_dwell_seconds",
            30,
        )
    ),
)

# Operator authorization is deliberately ephemeral.
# Every TruePanel process starts disarmed regardless of configuration.
thermal_operator_armed = False

# Live authority is granted only by a guarded runtime command.
# Configuration may enable the capability, but cannot arm it at boot.
thermal_dry_run = True

thermal_command_cooldown_seconds = float(
    thermal_policy_config.get(
        "command_cooldown_seconds",
        30,
    )
)

thermal_control_coordinator = (
    ThermalControlCoordinator(
        fan_control_runtime.service,
        policy_mode=thermal_policy_mode,
        operator_armed=thermal_operator_armed,
        dry_run=thermal_dry_run,
        command_cooldown_seconds=(
            thermal_command_cooldown_seconds
        ),
    )
)

thermal_fan_recommendation = None
thermal_observer_previous_profile = "automatic"
thermal_control_last_result = None

thermal_safety_current_fingerprint = (
    thermal_safety_fingerprint(config)
)
thermal_safety_commissioned_fingerprint = str(
    thermal_policy_config.get(
        "commissioned_fingerprint",
        "",
    )
    or ""
).strip().lower()

bounded_automatic_lease = BoundedAutomaticLease(
    commissioned_fingerprint=(
        thermal_safety_commissioned_fingerprint
    ),
    duration_seconds=AUTOMATIC_LEASE_SECONDS,
)

SUPERVISED_THERMAL_SESSION_SECONDS = 120.0
supervised_thermal_session_deadline = None


def publish_lcd_reader_status():
    """Publish a read-only snapshot of the LCD reader thread."""

    if lcd is None:
        return None

    try:
        return lcd_reader_status_bridge.publish(
            lcd.reader_snapshot()
        )
    except Exception:
        LOGGER.exception(
            "Unable to publish LCD reader status"
        )
        return None


def publish_fan_control_status(
    reason=None,
):
    payload = (
        fan_control_runtime
        .status_payload()
    )

    if reason is not None:
        payload[
            "last_reason"
        ] = reason

    recommendation = (
        thermal_fan_recommendation
    )

    payload[
        "thermal_policy_mode"
    ] = thermal_policy_mode

    payload[
        "thermal_operator_armed"
    ] = thermal_operator_armed

    payload[
        "thermal_dry_run"
    ] = (
        thermal_control_coordinator.dry_run
    )

    control_result = (
        thermal_control_last_result
    )

    payload[
        "thermal_control_state"
    ] = (
        control_result.state
        if control_result is not None
        else "awaiting_evaluation"
    )

    payload[
        "thermal_control_reason"
    ] = (
        control_result.reason
        if control_result is not None
        else (
            "Thermal control has not completed "
            "an evaluation cycle."
        )
    )

    payload[
        "thermal_simulated_profile"
    ] = (
        thermal_control_coordinator
        .simulated_profile
        .value
    )

    payload[
        "thermal_control_cooldown_remaining"
    ] = (
        control_result.cooldown_remaining
        if control_result is not None
        else 0.0
    )

    session_remaining = 0.0

    if supervised_thermal_session_deadline is not None:
        session_remaining = max(
            0.0,
            (
                supervised_thermal_session_deadline
                - time.monotonic()
            ),
        )

    payload[
        "thermal_supervised_session_active"
    ] = bool(
        supervised_thermal_session_deadline
        is not None
        and session_remaining > 0
    )

    payload[
        "thermal_supervised_session_remaining"
    ] = session_remaining

    payload[
        "thermal_automatic_lease_active"
    ] = bounded_automatic_lease.active()

    payload[
        "thermal_automatic_lease_remaining"
    ] = bounded_automatic_lease.remaining_seconds()

    payload[
        "thermal_automatic_lease_seconds"
    ] = AUTOMATIC_LEASE_SECONDS

    payload[
        "thermal_automatic_allowed_profiles"
    ] = sorted(
        AUTOMATIC_LEASE_ALLOWED_PROFILES
    )

    payload[
        "thermal_safety_fingerprint"
    ] = thermal_safety_current_fingerprint

    payload[
        "thermal_commissioned_fingerprint"
    ] = thermal_safety_commissioned_fingerprint

    payload[
        "thermal_commissioned_fingerprint_match"
    ] = bool(
        thermal_safety_commissioned_fingerprint
        and thermal_safety_current_fingerprint
        == thermal_safety_commissioned_fingerprint
    )

    if recommendation is None:
        payload[
            "thermal_recommended_profile"
        ] = "automatic"
        payload[
            "thermal_hottest_temperature_c"
        ] = None
        payload[
            "thermal_recommendation_reason"
        ] = (
            "Thermal observer is awaiting telemetry."
        )
        payload[
            "thermal_recommendation_changed"
        ] = False
        payload[
            "thermal_telemetry_valid"
        ] = False
    else:
        payload[
            "thermal_recommended_profile"
        ] = (
            recommendation
            .recommended_profile
            .value
        )
        payload[
            "thermal_hottest_temperature_c"
        ] = (
            recommendation
            .hottest_temperature_c
        )
        payload[
            "thermal_recommendation_reason"
        ] = recommendation.reason
        payload[
            "thermal_recommendation_changed"
        ] = bool(
            recommendation.changed
        )
        payload[
            "thermal_telemetry_valid"
        ] = bool(
            recommendation.telemetry_valid
        )

    fan_control_status_bridge.publish(
        payload
    )


def fan_command_telemetry():
    state = get_state(
        max_age=5
    )

    temperatures_c = []

    for item in (
        state.get(
            "temps",
            [],
        )
        or []
    ):
        if not isinstance(
            item,
            dict,
        ):
            continue

        value = item.get(
            "temperature_c",
            item.get(
                "temperature",
                item.get(
                    "temp"
                ),
            ),
        )

        try:
            temperatures_c.append(
                float(value)
            )
        except (
            TypeError,
            ValueError,
        ):
            continue

    last_updated = state.get(
        "last_updated"
    )
    telemetry_fresh = False

    try:
        telemetry_fresh = (
            time.time()
            - float(last_updated)
            <= 10
        )
    except (
        TypeError,
        ValueError,
    ):
        telemetry_fresh = False

    return {
        "fan_status": get_fan_status(),
        "temperatures_c": tuple(
            temperatures_c
        ),
        "telemetry_fresh": (
            telemetry_fresh
        ),
    }



def observe_thermal_fan_policy(
    telemetry=None,
):
    """
    Evaluate and publish thermal guidance without actuating fan control.

    The automatic_control mode is intentionally unarmed. This observer does
    not request profiles, invoke the command socket, or write fan hardware.
    """

    global thermal_fan_recommendation
    global thermal_observer_last_signature
    global thermal_observer_previous_profile

    if telemetry is None:
        telemetry = fan_command_telemetry()

    if thermal_policy_mode == "disabled":
        recommendation = (
            thermal_fan_policy.evaluate(
                (),
                telemetry_fresh=False,
            )
        )
    else:
        recommendation = (
            thermal_fan_policy.evaluate(
                telemetry.get(
                    "temperatures_c",
                    (),
                ),
                telemetry_fresh=bool(
                    telemetry.get(
                        "telemetry_fresh",
                        False,
                    )
                ),
            )
        )

    thermal_fan_recommendation = recommendation

    signature = (
        recommendation
        .recommended_profile
        .value,
        bool(
            recommendation.telemetry_valid
        ),
    )

    if (
        signature
        != thermal_observer_last_signature
    ):
        runtime_status = (
            fan_control_runtime
            .status_payload()
        )

        try:
            thermal_observer_history.append(
                event_from_recommendation(
                    recommendation,
                    active_profile=(
                        runtime_status.get(
                            "active_profile",
                            "automatic",
                        )
                    ),
                    control_authority=(
                        runtime_status.get(
                            "control_authority",
                            "automatic",
                        )
                    ),
                    policy_mode=thermal_policy_mode,
                    previous_recommended_profile=(
                        thermal_observer_previous_profile
                    ),
                )
            )
        except Exception:
            LOGGER.exception(
                "Could not append thermal "
                "observer history"
            )

        thermal_observer_last_signature = (
            signature
        )
        thermal_observer_previous_profile = (
            recommendation
            .recommended_profile
            .value
        )

    return recommendation


def record_thermal_commissioning_event(
    lifecycle_action,
    reason,
    *,
    lease_remaining=None,
):
    """Append one normalized commissioning lifecycle event."""

    runtime_status = (
        fan_control_runtime.status_payload()
    )

    if lease_remaining is None:
        if supervised_thermal_session_deadline is None:
            lease_remaining = 0.0
        else:
            lease_remaining = max(
                0.0,
                supervised_thermal_session_deadline
                - time.monotonic(),
            )

    state = thermal_commissioning_state(
        policy_mode=thermal_policy_mode,
        operator_armed=thermal_operator_armed,
        dry_run=(
            thermal_control_coordinator.dry_run
        ),
        supervised_session_active=(
            supervised_thermal_session_active()
        ),
    )

    try:
        thermal_commissioning_history.append(
            commissioning_event(
                lifecycle_action=lifecycle_action,
                reason=reason,
                commissioning_state=state,
                active_profile=runtime_status.get(
                    "active_profile",
                    "automatic",
                ),
                control_authority=runtime_status.get(
                    "control_authority",
                    "automatic",
                ),
                lease_remaining=lease_remaining,
            )
        )
    except Exception:
        LOGGER.exception(
            "Could not append thermal "
            "commissioning history"
        )


def record_fan_control_event(
    decision,
    telemetry,
    *,
    source,
):
    try:
        fan_control_history.append(
            event_from_decision(
                decision,
                source=source,
                telemetry=telemetry,
            )
        )
    except Exception:
        LOGGER.exception(
            "Could not append fan-control history"
        )


def fan_control_event_source(
    decision,
):
    reason_lower = decision.reason.lower()

    if (
        decision.force_automatic
        and "safety recovery confirmed"
        in reason_lower
    ):
        return "recovery"

    if (
        decision.force_automatic
        and "expired" in reason_lower
    ):
        return "timeout"

    return "safety"


def restore_motherboard_fan_control(
    reason,
    *,
    telemetry=None,
):
    """Synchronously restore controlled channels to motherboard Automatic."""

    current_telemetry = (
        telemetry
        if telemetry is not None
        else fan_command_telemetry()
    )

    runtime_status = (
        fan_control_runtime.status_payload()
    )

    if (
        runtime_status.get("active_profile")
        == "automatic"
        and runtime_status.get("control_authority")
        == "automatic"
    ):
        return None

    decision = (
        fan_control_runtime.service
        .request_profile(
            "automatic",
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
    )

    record_fan_control_event(
        decision,
        fan_command_telemetry(),
        source="thermal_policy",
    )

    publish_fan_control_status(
        reason=reason
    )

    return decision


def end_supervised_thermal_session(
    reason,
    *,
    lifecycle_action,
    telemetry=None,
):
    """End the live lease and return control to the motherboard."""

    global supervised_thermal_session_deadline
    global thermal_operator_armed
    global thermal_control_last_result

    supervised_thermal_session_deadline = None
    thermal_operator_armed = False

    current_telemetry = (
        telemetry
        if telemetry is not None
        else fan_command_telemetry()
    )

    restore_motherboard_fan_control(
        reason,
        telemetry=current_telemetry,
    )

    thermal_control_coordinator.configure(
        operator_armed=False,
        dry_run=True,
    )

    thermal_control_coordinator.simulated_profile = (
        thermal_control_coordinator._profile(
            "automatic"
        )
    )
    thermal_control_coordinator.owns_control = False

    thermal_control_last_result = None

    publish_fan_control_status(
        reason=reason
    )

    record_thermal_commissioning_event(
        lifecycle_action,
        reason,
        lease_remaining=0.0,
    )


def supervised_thermal_session_active():
    if supervised_thermal_session_deadline is None:
        return False

    return (
        time.monotonic()
        < supervised_thermal_session_deadline
    )


def end_bounded_automatic_lease(
    reason,
    *,
    lifecycle_action,
    telemetry=None,
    restore=True,
):
    """End Stage 1 automatic authority and return to motherboard control."""

    global thermal_operator_armed
    global thermal_control_last_result

    was_active = bounded_automatic_lease.cancel()
    thermal_operator_armed = False

    current_telemetry = (
        telemetry
        if telemetry is not None
        else fan_command_telemetry()
    )

    if restore:
        restore_motherboard_fan_control(
            reason,
            telemetry=current_telemetry,
        )

    thermal_control_coordinator.configure(
        operator_armed=False,
        dry_run=True,
    )
    thermal_control_coordinator.simulated_profile = (
        thermal_control_coordinator._profile(
            "automatic"
        )
    )
    thermal_control_coordinator.owns_control = False
    thermal_control_last_result = None

    publish_fan_control_status(
        reason=reason
    )

    if was_active:
        record_thermal_commissioning_event(
            lifecycle_action,
            reason,
            lease_remaining=0.0,
        )


def reconcile_fan_control():
    global thermal_control_last_result
    global thermal_operator_armed
    global supervised_thermal_session_deadline

    if not fan_control_runtime.connected:
        return None

    telemetry = fan_command_telemetry()
    recommendation = (
        observe_thermal_fan_policy(
            telemetry
        )
    )

    # Existing dead-man, emergency, and recovery logic owns the
    # first safety decision of every cycle.
    decision = fan_control_runtime.service.tick(
        fan_status=telemetry["fan_status"],
        temperatures_c=(
            telemetry["temperatures_c"]
        ),
        telemetry_fresh=(
            telemetry["telemetry_fresh"]
        ),
    )

    if decision is not None:
        source = fan_control_event_source(
            decision
        )

        post_transition_telemetry = (
            fan_command_telemetry()
        )

        record_fan_control_event(
            decision,
            post_transition_telemetry,
            source=source,
        )

        if bounded_automatic_lease.active():
            cancellation_reason = (
                "Bounded automatic thermal lease ended because "
                "the fan safety service changed control state."
            )

            end_bounded_automatic_lease(
                cancellation_reason,
                lifecycle_action=(
                    "automatic_lease_safety_cancelled"
                ),
                telemetry=post_transition_telemetry,
                restore=False,
            )

        elif (
            supervised_thermal_session_deadline
            is not None
        ):
            supervised_thermal_session_deadline = None
            thermal_operator_armed = False

            thermal_control_coordinator.configure(
                operator_armed=False,
                dry_run=True,
            )

            cancellation_reason = (
                "Supervised thermal session ended "
                "because the fan safety service "
                "changed control state."
            )

            publish_fan_control_status(
                reason=cancellation_reason
            )

            record_thermal_commissioning_event(
                "supervised_safety_cancelled",
                cancellation_reason,
                lease_remaining=0.0,
            )
        else:
            publish_fan_control_status()

        return decision

    if bounded_automatic_lease.deadline is not None:
        if not bounded_automatic_lease.active():
            end_bounded_automatic_lease(
                "Bounded automatic thermal lease expired; "
                "returned control to the motherboard.",
                lifecycle_action="automatic_lease_expired",
                telemetry=telemetry,
            )
            return None

        if not telemetry["telemetry_fresh"]:
            end_bounded_automatic_lease(
                "Bounded automatic thermal lease ended because "
                "telemetry became stale.",
                lifecycle_action=(
                    "automatic_lease_safety_cancelled"
                ),
                telemetry=telemetry,
            )
            return None

        if (
            recommendation.recommended_profile.value
            not in AUTOMATIC_LEASE_ALLOWED_PROFILES
        ):
            end_bounded_automatic_lease(
                "Bounded automatic thermal lease ended because "
                "the recommendation left the approved profile envelope.",
                lifecycle_action=(
                    "automatic_lease_safety_cancelled"
                ),
                telemetry=telemetry,
            )
            return None

    if supervised_thermal_session_deadline is not None:
        if not supervised_thermal_session_active():
            end_supervised_thermal_session(
                "Supervised thermal session expired; "
                "returned control to the motherboard.",
                lifecycle_action="supervised_expired",
                telemetry=telemetry,
            )
            return None

        if not telemetry["telemetry_fresh"]:
            end_supervised_thermal_session(
                "Supervised thermal session ended "
                "because telemetry became stale.",
                lifecycle_action=(
                    "supervised_safety_cancelled"
                ),
                telemetry=telemetry,
            )
            return None

        if (
            recommendation.recommended_profile.value
            != "balanced"
        ):
            end_supervised_thermal_session(
                "Supervised thermal session ended "
                "because the recommendation left "
                "the balanced profile.",
                lifecycle_action=(
                    "supervised_safety_cancelled"
                ),
                telemetry=telemetry,
            )
            return None

    thermal_control_last_result = (
        thermal_control_coordinator.evaluate(
            recommendation,
            telemetry=telemetry,
            runtime_status=(
                fan_control_runtime
                .status_payload()
            ),
        )
    )

    thermal_decision = (
        thermal_control_last_result
        .decision
    )

    if thermal_decision is not None:
        post_transition_telemetry = (
            fan_command_telemetry()
        )

        record_fan_control_event(
            thermal_decision,
            post_transition_telemetry,
            source="thermal_policy",
        )
        publish_fan_control_status()

    return thermal_decision


def set_thermal_operator_arm_state(
    action,
):
    """Apply a guarded runtime arm-state change.

    This first operator workflow intentionally supports dry-run only.
    Live thermal actuation remains locked out until separately enabled
    and reviewed.
    """

    global thermal_operator_armed
    global thermal_control_last_result
    global supervised_thermal_session_deadline

    normalized = str(
        action
    ).strip().lower()

    if normalized not in {
        "arm",
        "disarm",
        "supervised_live",
        "automatic_lease",
        "automatic_lease_renew",
    }:
        return {
            "ok": False,
            "status": "invalid_action",
            "message": (
                "Thermal-control action must be arm, disarm, "
                "supervised_live, automatic_lease, or "
                "automatic_lease_renew."
            ),
        }

    if thermal_policy_mode != "automatic_control":
        return {
            "ok": False,
            "status": "wrong_mode",
            "message": (
                "Thermal policy mode must be "
                "automatic_control."
            ),
            "policy_mode": thermal_policy_mode,
        }

    if (
        normalized == "arm"
        and not thermal_dry_run
    ):
        return {
            "ok": False,
            "status": "live_control_locked",
            "message": (
                "Standard runtime arming is limited "
                "to dry-run mode."
            ),
            "dry_run": False,
        }

    telemetry = fan_command_telemetry()
    runtime_status = (
        fan_control_runtime.status_payload()
    )

    if normalized == "automatic_lease":
        recommendation_profile = (
            thermal_fan_recommendation
            .recommended_profile
            .value
            if thermal_fan_recommendation is not None
            else "automatic"
        )

        lease_decision = bounded_automatic_lease.start(
            current_fingerprint=(
                thermal_safety_current_fingerprint
            ),
            active_profile=runtime_status.get(
                "active_profile",
                "automatic",
            ),
            recommended_profile=(
                recommendation_profile
            ),
            telemetry_valid=bool(
                thermal_fan_recommendation is not None
                and thermal_fan_recommendation
                .telemetry_valid
            ),
            telemetry_fresh=bool(
                telemetry.get(
                    "telemetry_fresh",
                    False,
                )
            ),
            connected=bool(
                runtime_status.get(
                    "connected",
                    False,
                )
            ),
            safety_hold=bool(
                runtime_status.get(
                    "safety_hold",
                    False,
                )
            ),
            recovery_pending=bool(
                runtime_status.get(
                    "recovery_pending",
                    False,
                )
            ),
        )

        if not lease_decision.accepted:
            return {
                "ok": False,
                "status": lease_decision.status,
                "message": lease_decision.message,
                "blocking_reasons": list(
                    lease_decision.blocking_reasons
                ),
                "operator_armed": (
                    thermal_operator_armed
                ),
                "dry_run": thermal_dry_run,
                "automatic_lease_active": False,
            }

        thermal_operator_armed = True

        thermal_control_coordinator.configure(
            operator_armed=True,
            dry_run=False,
        )

    elif normalized == "automatic_lease_renew":
        recommendation_profile = (
            thermal_fan_recommendation
            .recommended_profile
            .value
            if thermal_fan_recommendation is not None
            else "automatic"
        )

        lease_decision = bounded_automatic_lease.renew(
            current_fingerprint=(
                thermal_safety_current_fingerprint
            ),
            active_profile=runtime_status.get(
                "active_profile",
                "automatic",
            ),
            recommended_profile=(
                recommendation_profile
            ),
            telemetry_valid=bool(
                thermal_fan_recommendation is not None
                and thermal_fan_recommendation
                .telemetry_valid
            ),
            telemetry_fresh=bool(
                telemetry.get(
                    "telemetry_fresh",
                    False,
                )
            ),
            connected=bool(
                runtime_status.get(
                    "connected",
                    False,
                )
            ),
            safety_hold=bool(
                runtime_status.get(
                    "safety_hold",
                    False,
                )
            ),
            recovery_pending=bool(
                runtime_status.get(
                    "recovery_pending",
                    False,
                )
            ),
        )

        if not lease_decision.accepted:
            return {
                "ok": False,
                "status": lease_decision.status,
                "message": lease_decision.message,
                "blocking_reasons": list(
                    lease_decision.blocking_reasons
                ),
                "operator_armed": (
                    thermal_operator_armed
                ),
                "dry_run": thermal_dry_run,
                "automatic_lease_active": (
                    bounded_automatic_lease.active()
                ),
                "automatic_lease_remaining": (
                    bounded_automatic_lease
                    .remaining_seconds()
                ),
            }

        thermal_operator_armed = True

        thermal_control_coordinator.configure(
            operator_armed=True,
            dry_run=False,
        )

    elif normalized == "supervised_live":
        blocking_reasons = []

        if not thermal_dry_run:
            blocking_reasons.append(
                "The supervised session must begin "
                "from dry-run mode."
            )

        if thermal_fan_recommendation is None:
            blocking_reasons.append(
                "Thermal recommendation is unavailable."
            )
        elif not bool(
            thermal_fan_recommendation
            .telemetry_valid
        ):
            blocking_reasons.append(
                "Thermal recommendation telemetry "
                "is invalid."
            )
        elif (
            thermal_fan_recommendation
            .recommended_profile
            .value
            != "balanced"
        ):
            blocking_reasons.append(
                "Supervised live control permits "
                "only the balanced recommendation."
            )

        if not bool(
            telemetry.get(
                "telemetry_fresh",
                False,
            )
        ):
            blocking_reasons.append(
                "Thermal telemetry is stale."
            )

        if not bool(
            runtime_status.get(
                "connected",
                False,
            )
        ):
            blocking_reasons.append(
                "Fan-control runtime is disconnected."
            )

        if (
            runtime_status.get(
                "active_profile"
            )
            != "automatic"
        ):
            blocking_reasons.append(
                "Supervised live control must begin "
                "from motherboard automatic mode."
            )

        if bool(
            runtime_status.get(
                "safety_hold",
                False,
            )
        ):
            blocking_reasons.append(
                "Fan-control safety hold is active."
            )

        if bool(
            runtime_status.get(
                "recovery_pending",
                False,
            )
        ):
            blocking_reasons.append(
                "Fan-control safety recovery is pending."
            )

        fan_channels = (
            telemetry
            .get("fan_status", {})
            .get("fan_channels", [])
        )

        controlled = {
            int(item.get("number")): item
            for item in fan_channels
            if isinstance(item, dict)
            and item.get("number") in (1, 2)
        }

        for channel in (1, 2):
            item = controlled.get(channel)

            if item is None:
                blocking_reasons.append(
                    f"Controlled fan {channel} "
                    "telemetry is unavailable."
                )
                continue

            try:
                rpm = float(
                    item.get("rpm", 0)
                )
            except (
                TypeError,
                ValueError,
            ):
                rpm = 0.0

            if rpm < 300:
                blocking_reasons.append(
                    f"Controlled fan {channel} "
                    "is below the safe RPM floor."
                )

            if bool(
                item.get("alarm", False)
            ):
                blocking_reasons.append(
                    f"Controlled fan {channel} "
                    "reports an alarm."
                )

        if blocking_reasons:
            return {
                "ok": False,
                "status": "readiness_blocked",
                "message": blocking_reasons[0],
                "blocking_reasons": blocking_reasons,
                "operator_armed": (
                    thermal_operator_armed
                ),
                "dry_run": thermal_dry_run,
            }

        thermal_operator_armed = True

        thermal_control_coordinator.configure(
            operator_armed=True,
            dry_run=False,
        )

        supervised_thermal_session_deadline = (
            time.monotonic()
            + SUPERVISED_THERMAL_SESSION_SECONDS
        )

    elif normalized == "arm":
        blocking_reasons = []

        if thermal_fan_recommendation is None:
            blocking_reasons.append(
                "Thermal recommendation is unavailable."
            )
        elif not bool(
            thermal_fan_recommendation
            .telemetry_valid
        ):
            blocking_reasons.append(
                "Thermal recommendation telemetry "
                "is invalid."
            )

        if not bool(
            telemetry.get(
                "telemetry_fresh",
                False,
            )
        ):
            blocking_reasons.append(
                "Thermal telemetry is stale."
            )

        if not bool(
            runtime_status.get(
                "connected",
                False,
            )
        ):
            blocking_reasons.append(
                "Fan-control runtime is disconnected."
            )

        if bool(
            runtime_status.get(
                "safety_hold",
                False,
            )
        ):
            blocking_reasons.append(
                "Fan-control safety hold is active."
            )

        if blocking_reasons:
            return {
                "ok": False,
                "status": "readiness_blocked",
                "message": blocking_reasons[0],
                "blocking_reasons": (
                    blocking_reasons
                ),
                "operator_armed": (
                    thermal_operator_armed
                ),
                "dry_run": thermal_dry_run,
            }

        thermal_operator_armed = True
        thermal_control_coordinator.configure(
            operator_armed=True
        )

    else:
        was_supervised = (
            supervised_thermal_session_deadline
            is not None
        )
        was_automatic_lease = (
            bounded_automatic_lease.deadline
            is not None
        )

        bounded_automatic_lease.cancel()
        supervised_thermal_session_deadline = None
        thermal_operator_armed = False

        restore_motherboard_fan_control(
            (
                "Automatic thermal control disarmed; "
                "motherboard control restored."
            ),
            telemetry=telemetry,
        )

        thermal_control_coordinator.configure(
            operator_armed=False,
            dry_run=True,
        )
        thermal_control_coordinator.simulated_profile = (
            thermal_control_coordinator._profile(
                "automatic"
            )
        )
        thermal_control_coordinator.owns_control = False
        thermal_control_last_result = None

        if was_automatic_lease:
            record_thermal_commissioning_event(
                "automatic_lease_cancelled",
                (
                    "Bounded automatic thermal control "
                    "manually cancelled; motherboard "
                    "control restored."
                ),
                lease_remaining=0.0,
            )

        if was_supervised:
            record_thermal_commissioning_event(
                "supervised_disarmed",
                (
                    "Automatic thermal control "
                    "manually disarmed; motherboard "
                    "control restored."
                ),
                lease_remaining=0.0,
            )

    if (
        normalized != "disarm"
        and thermal_fan_recommendation is not None
    ):
        thermal_control_last_result = (
            thermal_control_coordinator
            .evaluate(
                thermal_fan_recommendation,
                telemetry=telemetry,
                runtime_status=runtime_status,
            )
        )

    if (
        normalized == "automatic_lease"
        and bounded_automatic_lease.active()
    ):
        record_thermal_commissioning_event(
            "automatic_lease_started",
            (
                "Bounded automatic thermal control "
                "engaged for 86400 seconds with balanced "
                "and cooling boost profiles only."
            ),
            lease_remaining=AUTOMATIC_LEASE_SECONDS,
        )

    if (
        normalized == "automatic_lease_renew"
        and bounded_automatic_lease.active()
    ):
        record_thermal_commissioning_event(
            "automatic_lease_renewed",
            (
                "Stage 3 automatic thermal control "
                "renewed for 86400 seconds."
            ),
            lease_remaining=AUTOMATIC_LEASE_SECONDS,
        )

    if (
        normalized == "supervised_live"
        and supervised_thermal_session_active()
    ):
        record_thermal_commissioning_event(
            "supervised_started",
            (
                "Supervised live thermal control "
                "engaged for 120 seconds with the "
                "balanced profile only."
            ),
            lease_remaining=(
                SUPERVISED_THERMAL_SESSION_SECONDS
            ),
        )

    return {
        "ok": True,
        "status": (
            "automatic_lease_renewed"
            if (
                normalized == "automatic_lease_renew"
                and thermal_operator_armed
            )
            else (
                "automatic_lease"
                if (
                    normalized == "automatic_lease"
                    and thermal_operator_armed
                )
            else (
                "supervised_live"
                if (
                    normalized == "supervised_live"
                    and thermal_operator_armed
                )
                else (
                    "armed"
                    if thermal_operator_armed
                    else "disarmed"
                )
            )
        )
        ),
        "message": (
            (
                "Stage 3 automatic thermal control "
                "renewed for 86400 seconds."
            )
            if (
                normalized == "automatic_lease_renew"
                and thermal_operator_armed
            )
            else (
            (
                "Bounded automatic thermal control "
                "engaged for 86400 seconds with balanced "
                "and cooling boost profiles only."
            )
            if (
                normalized == "automatic_lease"
                and thermal_operator_armed
            )
            else (
                (
                    "Supervised live thermal control "
                    "engaged for 120 seconds with the "
                    "balanced profile only."
                )
                if (
                    normalized == "supervised_live"
                    and thermal_operator_armed
                )
                else (
                    "Automatic thermal control armed "
                    "in dry-run mode."
                    if thermal_operator_armed
                    else (
                        "Automatic thermal control disarmed; "
                        "motherboard control restored."
                    )
                )
            )
        )
        ),
        "operator_armed": (
            thermal_operator_armed
        ),
        "dry_run": (
            thermal_control_coordinator.dry_run
        ),
        "policy_mode": thermal_policy_mode,
        "supervised_session_active": (
            supervised_thermal_session_active()
        ),
        "supervised_session_seconds": (
            SUPERVISED_THERMAL_SESSION_SECONDS
            if supervised_thermal_session_active()
            else 0.0
        ),
        "automatic_lease_active": (
            bounded_automatic_lease.active()
        ),
        "automatic_lease_seconds": (
            AUTOMATIC_LEASE_SECONDS
            if bounded_automatic_lease.active()
            else 0.0
        ),
        "automatic_lease_remaining": (
            bounded_automatic_lease
            .remaining_seconds()
        ),
        "simulated_profile": (
            thermal_control_coordinator
            .simulated_profile
            .value
        ),
    }


def build_fan_command_server():
    if not fan_control_runtime.enabled:
        return None

    processor = FanCommandProcessor(
        fan_control_runtime,
        telemetry_provider=(
            fan_command_telemetry
        ),
        status_publisher=(
            publish_fan_control_status
        ),
        event_recorder=lambda decision, telemetry: (
            record_fan_control_event(
                decision,
                fan_command_telemetry(),
                source="manual",
            )
        ),
        thermal_control_handler=(
            set_thermal_operator_arm_state
        ),
    )

    return FanCommandServer(
        processor
    )


def lcd_on():
    global lcd_timer

    lcd.backlight(True)

    if lcd_timer:
        lcd_timer.cancel()

    lcd_timer = threading.Timer(
        DISPLAY_TIMEOUT,
        lambda: lcd.backlight(False),
    )
    lcd_timer.daemon = True
    lcd_timer.start()


def shell(cmd):
    return subprocess.check_output(cmd, shell=True, universal_newlines=True).strip()


def refresh_state(force_history=False):
    """
    Refresh collector data and offer the new state to historical telemetry.

    HistoryStore enforces its own sampling interval, so frequent collector
    refreshes do not become frequent disk writes.
    """

    state = collector.update()

    history_recorder.record(
        state,
        alert_count=len(alert_manager.get_history()),
        force=force_history,
    )

    return state


def get_state(max_age=5):
    last = collector.state.get("last_updated")
    now = time.time()

    if last is None or now - last > max_age:
        return refresh_state()

    return collector.state


def write_lines(line1, line2, delay=1):
    lcd.clear()
    lcd.write(0, [line1[:16], line2[:16]])
    time.sleep(delay)


def show_startup_splash():
    write_lines("TruePanel", "Flight Deck", 1)
    write_lines("Collector", "Online", 1)
    write_lines("Mission Ctrl", "Online", 1)
    write_lines("AutoPilot", "Online", 1)
    write_lines("Display", "Ready", 1)

    try:
        state = refresh_state(force_history=True)
        frame = autopilot.frame(state)
        write_lines(frame.line1, frame.line2, 2)
    except Exception:
        write_lines("TruePanel", "Ready", 2)


def show_version():
    sys_name = platform.node()
    sys_vers = f"{platform.system()} ({platform.machine()})"

    lcd.clear()
    lcd.write(0, [sys_name[:16], sys_vers[:16]])


def show_truenas():
    if os.path.exists("/.dockerenv"):
        lines = ["TruePanel", "Docker Mode"]
    else:
        try:
            truenas = shell("cli -c 'system version'")
            truenas = truenas.split("-")
            lines = ["-".join(truenas[:-1]), truenas[-1]]
        except Exception:
            lines = ["TruePanel", "Native Mode"]

    lcd.clear()
    lcd.write(0, [lines[0][:16], lines[1][:16]])


def show_uptime():
    uptime = shell("uptime").split(",")
    up = " ".join(uptime[0].split()[2:]) + " " + uptime[1]
    load = os.getloadavg()

    lcd.clear()
    lcd.write(0, [f"Up: {up}"[:16], f"Load: {load[0]:.2f}"[:16]])


def show_cpu_ram():
    state = get_state()

    lcd.clear()
    lcd.write(0, [
        f"CPU {state.get('cpu_percent', 0)}%",
        f"RAM {state.get('ram_percent', 0)}%",
    ])


def show_pool_health():
    state = get_state()
    pools = state.get("pools", [])

    lcd.clear()

    if not pools:
        lcd.write(0, ["Pool Health", "No Pool Data"])
        return

    bad = [p for p in pools if p.get("health") != "ONLINE"]

    if bad:
        pool = bad[0]
        lcd.write(0, ["Pool Alert", f"{pool['name'][:8]} {pool['health'][:7]}"])
    else:
        lcd.write(0, ["Pool Health", "All Healthy"])


def add_ips_to_menu():
    def get_kind(iface):
        if "linkinfo" in iface:
            if "info_kind" in iface["linkinfo"]:
                return iface["linkinfo"]["info_kind"]

        return ""

    def get_ipv4(iface):
        if "addr_info" in iface:
            for addr in iface["addr_info"]:
                if addr["family"] == "inet":
                    return addr["local"]

        return "0.0.0.0"

    try:
        ip_json = json.loads(shell("ip -details -json address show"))
    except Exception:
        return

    ip_addresses.clear()

    for iface in ip_json:
        if iface["link_type"] == "loopback":
            continue

        if get_kind(iface) not in ["", "tun"]:
            continue

        ip_addresses.append((iface["ifname"], get_ipv4(iface)))

    while show_ip in menu:
        menu.remove(show_ip)

    for _ in ip_addresses:
        menu.append(show_ip)


def show_ip():
    ip_index = 0

    for index in range(menu_item):
        if menu[index] == show_ip:
            ip_index += 1

    lcd.clear()

    if not ip_addresses:
        lcd.write(0, ["Network", "No IP Data"])
        return

    lcd.write(0, [
        f"{ip_addresses[ip_index][0]}"[:16],
        f"{ip_addresses[ip_index][1]}"[:16],
    ])


def add_zpools_to_menu():
    pools = shell("zpool list").split("\n")

    zfs_pools.clear()

    for pool in pools[1:]:
        zfs_pools.append(pool.split())

    while show_zpool in menu:
        menu.remove(show_zpool)

    for _ in zfs_pools:
        menu.append(show_zpool)


def show_zpool():
    state = get_state()
    pools = state.get("pools", [])

    lcd.clear()

    if not pools:
        lcd.write(0, ["Storage", "No Pool Data"])
        return

    pool = pools[menu_item % len(pools)]
    name = pool.get("name", "pool")
    health = pool.get("health", "UNKNOWN")
    capacity = pool.get("capacity", "0%")

    try:
        pct = int(str(capacity).strip("%"))
    except Exception:
        pct = 0

    if health != "ONLINE":
        lcd.write(0, [f"{name[:8]} {health[:7]}", f"{pct}% Used"])
    else:
        lcd.write(0, [f"{name[:8]} {pct}%", progress_bar(pct)])


def show_drive_temps():
    state = get_state()
    temps = state.get("temps", [])

    lcd.clear()

    if not temps:
        lcd.write(0, ["Drive Temps", "No SMART Data"])
        return

    drive_info = temps[menu_item % len(temps)]
    drive = drive_info.get("drive", "disk")
    temp = drive_info.get("temp", 0)

    if temp >= 50:
        lcd.write(0, ["HOT DRIVE", f"{drive[:10]} {temp} C"])
    else:
        lcd.write(0, [f"Drive {drive[:10]}", f"Temp {temp} C"])


def show_fan_rpm():
    lcd.clear()
    lcd.write(0, fan_rpm_page())


def show_fan_control():
    status = fan_control_status_bridge.read(
        max_age=30.0
    )

    lcd.clear()
    lcd.write(
        0,
        fan_control_page(
            status
        ),
    )


def show_fan_pwm():
    lcd.clear()
    lcd.write(0, fan_pwm_page())


def cached_display_state():
    """
    Return the latest collector snapshot without refreshing hardware.

    Physical button navigation must remain responsive even when the normal
    telemetry refresh interval has elapsed. The main loop owns fresh
    collection; button callbacks only render the most recent safe snapshot.
    """

    state = dict(
        collector.state
        or {}
    )

    if state:
        return state

    return get_state()


def render_mission_frame(frame):
    """Render one complete Mission Home frame."""

    lcd.clear()
    lcd.write(0, frame.lines)


def show_mission_home():
    state = get_state()
    frame = autopilot.tick(state)

    render_mission_frame(frame)


def next_mission_dashboard():
    state = cached_display_state()
    frame = autopilot.next(state)

    render_mission_frame(frame)



def previous_mission_dashboard():
    state = cached_display_state()
    frame = autopilot.previous(state)

    render_mission_frame(frame)



def show_mission_control():
    state = refresh_state()
    frame = display_manager.evaluate(state)

    lcd.clear()
    lcd.write(0, frame.lines)

    return frame


def show_event_queue():
    frame = display_manager.render_event_queue()

    lcd.clear()
    lcd.write(0, frame.lines)


def next_event_queue():
    frame = display_manager.next_event_queue()

    lcd.clear()
    lcd.write(0, frame.lines)


def show_alert_history():
    frame = display_manager.render_history()

    lcd.clear()
    lcd.write(0, frame.lines)


def next_alert_history():
    frame = display_manager.next_history()

    lcd.clear()
    lcd.write(0, frame.lines)


def show_alert_transition(frame):
    lcd.clear()
    lcd.write(0, frame.lines)

def request_shutdown(signum=None, frame=None):
    global shutdown_requested
    shutdown_requested = True


def maybe_show_alert():
    state = refresh_state()
    frame = display_manager.evaluate(state)

    if frame.interrupt:
        if alert_manager.should_beep(frame.event):
            buzzer.alert(frame.priority)

        show_alert_transition(frame)
        time.sleep(frame.event.timeout)
        return True

    return False


menu = [
    show_mission_home,
    show_truenas,
    show_version,
    show_uptime,
    show_cpu_ram,
    show_pool_health,
    show_zpool,
    show_drive_temps,
    show_fan_rpm,
    show_fan_control,
    show_fan_pwm,
]


def response_handler(command, data):
    global menu_item

    callback_started = time.perf_counter()
    page_name = (
        menu[menu_item].__name__
        if menu
        else "unknown"
    )

    try:
        if command != "Switch_Status":
            return

        # The controller reports zero when a button is released. Release
        # frames must not wake the backlight or trigger another render.
        if not data:
            return

        lcd_on()
        prev_menu = menu_item

        if menu[menu_item] == show_mission_home:
            if data == 0x01:
                previous_mission_dashboard()
                return

            if data == 0x02:
                next_mission_dashboard()
                return

        if data == 0x01:
            menu_item = (menu_item - 1) % len(menu)

        if data == 0x02:
            menu_item = (menu_item + 1) % len(menu)

        if prev_menu != menu_item:
            page_name = menu[
                menu_item
            ].__name__
            menu[menu_item]()

    finally:
        total_ms = (
            time.perf_counter()
            - callback_started
        ) * 1000.0

        if (
            command == "Switch_Status"
            and data
            and total_ms >= 750.0
        ):
            LOGGER.warning(
                (
                    "Abnormal LCD button latency: "
                    "button=0x%04X "
                    "page=%s "
                    "duration_ms=%.3f"
                ),
                data,
                page_name,
                total_ms,
            )



def main():
    global lcd, menu_item
    global fan_command_server

    signal.signal(signal.SIGTERM, request_shutdown)
    signal.signal(signal.SIGINT, request_shutdown)

    lcd = qnaplcd.QnapLCD(
        PORT,
        PORT_SPEED,
        response_handler,
    )

    publish_lcd_reader_status()

    lcd_on()
    lcd.reset()
    lcd.clear()

    try:
        observe_thermal_fan_policy()
        publish_fan_control_status()

        fan_command_server = (
            build_fan_command_server()
        )

        if fan_command_server is not None:
            fan_command_server.start()

        if bay_led_startup_animation is not None:
            bay_led_startup_animation.run()

        show_startup_splash()
        buzzer.startup()
        publish_lcd_reader_status()

        while not shutdown_requested:
            try:
                reconcile_fan_control()
            except Exception:
                LOGGER.exception(
                    "Fan-control reconciliation failed"
                )

            observe_thermal_fan_policy()
            publish_fan_control_status()
            publish_lcd_reader_status()
            add_ips_to_menu()

            maybe_show_alert()
            menu[menu_item]()

            delay = 5

            for _ in range(delay * 10):
                if shutdown_requested:
                    break

                time.sleep(0.1)

            if not shutdown_requested:
                menu_item = (
                    menu_item + 1
                ) % len(menu)
    finally:
        if fan_command_server is not None:
            try:
                fan_command_server.stop()
            except Exception:
                pass
            finally:
                fan_command_server = None

        try:
            fan_control_runtime.shutdown()
        except Exception:
            pass

        try:
            publish_fan_control_status(
                "TruePanel is shutting down; "
                "Automatic restoration requested."
            )
        except Exception:
            pass

        if lcd_timer is not None:
            lcd_timer.cancel()

        publish_lcd_reader_status()

        try:
            buzzer.shutdown()
            write_lines(
                "TruePanel",
                "Shutting Down",
                0.5,
            )
            lcd.backlight(False)
        except Exception:
            pass
        finally:
            try:
                lcd.close()
            except Exception:
                pass

main()
