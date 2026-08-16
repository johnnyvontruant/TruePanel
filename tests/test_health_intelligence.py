from truepanel.health import (
    HealthEvaluator,
    HealthResult,
    HealthState,
)


def test_aggregate_nominal_ignores_unknown_without_hiding_known_health():
    result = HealthEvaluator.aggregate(
        [
            HealthResult(
                HealthState.NOMINAL,
                "ok",
                "ok",
                "none",
            ),
            HealthResult(
                HealthState.UNKNOWN,
                "unknown",
                "unknown",
                "check",
            ),
        ]
    )

    assert result.state is HealthState.NOMINAL
    assert result.summary == "System nominal"


def test_aggregate_uses_highest_known_severity():
    result = HealthEvaluator.aggregate(
        [
            HealthResult(
                HealthState.ATTENTION,
                "attention",
                "attention reason",
                "watch",
            ),
            HealthResult(
                HealthState.CRITICAL,
                "critical",
                "critical reason",
                "act",
            ),
            HealthResult(
                HealthState.UNKNOWN,
                "unknown",
                "unknown reason",
                "check",
            ),
        ]
    )

    assert result.state is HealthState.CRITICAL
    assert result.summary == "critical"
    assert result.reason == "critical reason"


def test_aggregate_all_unknown_returns_unknown():
    result = HealthEvaluator.aggregate(
        [
            HealthResult(
                HealthState.UNKNOWN,
                "unknown",
                "unknown",
                "check",
            )
        ]
    )

    assert result.state is HealthState.UNKNOWN


def test_evaluator_reports_nominal_known_subsystems():
    payload = HealthEvaluator().evaluate(
        fans={
            "available": True,
            "channels": [
                {
                    "number": 1,
                    "label": "Rear Fan 1",
                    "monitored": True,
                    "rpm": 1500,
                    "alarm": False,
                },
                {
                    "number": 2,
                    "label": "Rear Fan 2",
                    "monitored": True,
                    "rpm": 1450,
                    "alarm": False,
                },
            ],
            "control": {
                "available": True,
                "safety_hold": False,
                "recovery_pending": False,
            },
        },
        storage={
            "pools": [
                {
                    "name": "HDDs",
                    "health": "ONLINE",
                }
            ]
        },
        network=[
            {
                "name": "enp116s0",
                "label": "Ethernet Port 2",
                "primary": True,
                "link_up": True,
            }
        ],
        lcd={
            "available": True,
            "stale": False,
            "reader": {
                "healthy": True,
                "connected": True,
            },
        },
        capabilities={},
    )

    assert payload["state"] == "NOMINAL"
    assert payload["summary"] == "System nominal"
    assert payload["unknown_subsystems"] == 1
    assert payload["subsystems"]["services"]["state"] == "UNKNOWN"


def test_monitored_fan_alarm_degrades_cooling_and_overall_health():
    payload = HealthEvaluator().evaluate(
        fans={
            "available": True,
            "channels": [
                {
                    "number": 2,
                    "label": "Rear Fan 2",
                    "monitored": True,
                    "rpm": 0,
                    "alarm": True,
                }
            ],
            "control": {
                "available": True,
                "safety_hold": False,
                "recovery_pending": False,
            },
        },
        storage={
            "pools": [
                {
                    "name": "HDDs",
                    "health": "ONLINE",
                }
            ]
        },
        network=[
            {
                "primary": True,
                "link_up": True,
            }
        ],
        lcd={
            "available": True,
            "stale": False,
            "reader": {
                "healthy": True,
                "connected": True,
            },
        },
    )

    assert payload["state"] == "DEGRADED"
    assert payload["subsystems"]["cooling"]["state"] == "DEGRADED"
    assert "Rear Fan 2" in payload["subsystems"]["cooling"]["reason"]


def test_unmonitored_fan_alarm_does_not_degrade_cooling():
    payload = HealthEvaluator().evaluate(
        fans={
            "available": True,
            "channels": [
                {
                    "number": 1,
                    "label": "Rear Fan 1",
                    "monitored": True,
                    "rpm": 1500,
                    "alarm": False,
                },
                {
                    "number": 3,
                    "label": "Unused Header",
                    "monitored": False,
                    "rpm": 0,
                    "alarm": True,
                },
            ],
            "control": {
                "available": True,
                "safety_hold": False,
                "recovery_pending": False,
            },
        },
    )

    assert payload["subsystems"]["cooling"]["state"] == "NOMINAL"


def test_thermal_safety_hold_degrades_health():
    payload = HealthEvaluator().evaluate(
        fans={
            "available": True,
            "channels": [
                {
                    "number": 1,
                    "monitored": True,
                    "rpm": 1400,
                    "alarm": False,
                }
            ],
            "control": {
                "available": True,
                "safety_hold": True,
                "recovery_pending": False,
                "thermal_control_reason": "Telemetry freshness lost.",
            },
        }
    )

    assert payload["subsystems"]["thermal"]["state"] == "DEGRADED"
    assert payload["state"] == "DEGRADED"
    assert payload["reason"] == "Telemetry freshness lost."


def test_thermal_recovery_pending_requires_attention():
    payload = HealthEvaluator().evaluate(
        fans={
            "available": True,
            "channels": [
                {
                    "number": 1,
                    "monitored": True,
                    "rpm": 1400,
                    "alarm": False,
                }
            ],
            "control": {
                "available": True,
                "safety_hold": False,
                "recovery_pending": True,
                "last_reason": "Waiting for healthy cycles.",
            },
        }
    )

    assert payload["subsystems"]["thermal"]["state"] == "ATTENTION"


def test_faulted_pool_is_critical():
    payload = HealthEvaluator().evaluate(
        storage={
            "pools": [
                {
                    "name": "HDDs",
                    "health": "FAULTED",
                }
            ]
        }
    )

    assert payload["subsystems"]["storage"]["state"] == "CRITICAL"
    assert payload["state"] == "CRITICAL"


def test_degraded_pool_is_degraded():
    payload = HealthEvaluator().evaluate(
        storage={
            "pools": [
                {
                    "name": "HDDs",
                    "health": "DEGRADED",
                }
            ]
        }
    )

    assert payload["subsystems"]["storage"]["state"] == "DEGRADED"


def test_unknown_pool_state_requires_attention_without_inventing_severity():
    payload = HealthEvaluator().evaluate(
        storage={
            "pools": [
                {
                    "name": "HDDs",
                    "health": "SUSPENDED",
                }
            ]
        }
    )

    assert payload["subsystems"]["storage"]["state"] == "ATTENTION"


def test_primary_network_link_down_is_degraded():
    payload = HealthEvaluator().evaluate(
        network=[
            {
                "name": "enp116s0",
                "label": "Ethernet Port 2",
                "primary": True,
                "link_up": False,
            }
        ]
    )

    assert payload["subsystems"]["network"]["state"] == "DEGRADED"


def test_link_up_without_primary_requires_attention():
    payload = HealthEvaluator().evaluate(
        network=[
            {
                "name": "enp116s0",
                "link_up": True,
                "primary": False,
            }
        ]
    )

    assert payload["subsystems"]["network"]["state"] == "ATTENTION"


def test_stale_front_panel_requires_attention():
    payload = HealthEvaluator().evaluate(
        lcd={
            "available": True,
            "stale": True,
            "reader": {
                "healthy": True,
                "connected": True,
            },
        }
    )

    assert payload["subsystems"]["front_panel"]["state"] == "ATTENTION"


def test_unhealthy_front_panel_reader_is_degraded():
    payload = HealthEvaluator().evaluate(
        lcd={
            "available": True,
            "stale": False,
            "reader": {
                "healthy": False,
                "connected": False,
                "connection_error": "serial disconnected",
            },
        }
    )

    assert payload["subsystems"]["front_panel"]["state"] == "DEGRADED"
    assert payload["subsystems"]["front_panel"]["reason"] == "serial disconnected"


def test_services_remain_unknown_until_true_runtime_service_health_exists():
    payload = HealthEvaluator().evaluate(
        capabilities={
            "dashboard": {
                "status": True,
            },
            "safety": {
                "read_only": True,
            },
        }
    )

    assert payload["subsystems"]["services"]["state"] == "UNKNOWN"

def test_services_nominal_when_all_required_units_are_active():
    payload = HealthEvaluator().evaluate(
        services={
            "available": True,
            "services": [
                {
                    "name": "truepanel.service",
                    "required": True,
                    "observed": True,
                    "load_state": "loaded",
                    "active_state": "active",
                    "sub_state": "running",
                },
                {
                    "name": "truepanel-mission-control.service",
                    "required": True,
                    "observed": True,
                    "load_state": "loaded",
                    "active_state": "active",
                    "sub_state": "running",
                },
            ],
        },
    )

    services = payload["subsystems"]["services"]

    assert services["state"] == "NOMINAL"
    assert services["summary"] == "TruePanel services nominal"


def test_failed_required_service_degrades_health():
    payload = HealthEvaluator().evaluate(
        services={
            "available": True,
            "services": [
                {
                    "name": "truepanel.service",
                    "required": True,
                    "observed": True,
                    "load_state": "loaded",
                    "active_state": "failed",
                    "sub_state": "failed",
                },
                {
                    "name": "truepanel-mission-control.service",
                    "required": True,
                    "observed": True,
                    "load_state": "loaded",
                    "active_state": "active",
                    "sub_state": "running",
                },
            ],
        },
    )

    services = payload["subsystems"]["services"]

    assert payload["state"] == "DEGRADED"
    assert services["state"] == "DEGRADED"
    assert "truepanel.service" in services["reason"]


def test_unavailable_service_observation_remains_unknown():
    payload = HealthEvaluator().evaluate(
        services={
            "available": False,
            "services": [],
        },
    )

    services = payload["subsystems"]["services"]

    assert services["state"] == "UNKNOWN"


def test_known_service_failure_wins_over_incomplete_observation():
    payload = HealthEvaluator().evaluate(
        services={
            "available": True,
            "services": [
                {
                    "name": "truepanel.service",
                    "required": True,
                    "observed": True,
                    "load_state": "loaded",
                    "active_state": "failed",
                    "sub_state": "failed",
                },
                {
                    "name": (
                        "truepanel-mission-control.service"
                    ),
                    "required": True,
                    "observed": False,
                    "load_state": "unavailable",
                    "active_state": "unavailable",
                    "sub_state": "unavailable",
                },
            ],
        },
    )

    services = payload["subsystems"]["services"]

    assert payload["state"] == "DEGRADED"
    assert services["state"] == "DEGRADED"
    assert "truepanel.service" in services["reason"]
