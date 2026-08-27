from truepanel.holodeck.oracle_lab import (
    drive_degradation,
    fan_bearing_degradation,
    network_path_degradation,
    run_oracle_scenario,
)
from truepanel.oracle import (
    DEFAULT_CORRELATIONS,
    OracleEngine,
    OracleState,
    simulate_drive_failure,
)


def _warm_fan_baseline(engine: OracleEngine) -> None:
    for index in range(12):
        engine.observe(
            timestamp=float(index),
            metrics={
                "fan.pwm": 180.0 + ((index % 3) - 1),
                "fan.rpm": 1500.0 + ((index % 5) - 2) * 4.0,
            },
        )


def test_oracle_stable_noise_remains_normal() -> None:
    engine = OracleEngine()
    outlook = None

    for index in range(40):
        outlook = engine.observe(
            timestamp=float(index),
            metrics={
                "fan.pwm": 180.0 + ((index % 3) - 1),
                "fan.rpm": 1500.0 + ((index % 5) - 2) * 4.0,
                "drive.temperature_c": 35.0 + ((index % 3) - 1) * 0.1,
            },
        )

    assert outlook is not None
    assert outlook["state"] == "NORMAL"
    assert outlook["read_only"] is True
    assert outlook["predictive_authority"] is False
    assert outlook["confidence"] == 1.0
    assert outlook["correlations"] == []


def test_statistics_cannot_invent_hard_fault() -> None:
    engine = OracleEngine()
    _warm_fan_baseline(engine)

    outlook = engine.observe(
        timestamp=20.0,
        metrics={"fan.pwm": 255.0, "fan.rpm": 100.0},
    )

    assert outlook["state"] == OracleState.DEVELOPING.value
    assert all(
        metric["state"] != OracleState.FAULT.value
        for metric in outlook["metrics"].values()
    )

    hard_fault = engine.observe(
        timestamp=21.0,
        metrics={"fan.pwm": 255.0, "fan.rpm": 0.0},
        hard_faults=("fan.rpm",),
    )
    assert hard_fault["state"] == OracleState.FAULT.value
    assert hard_fault["metrics"]["fan.rpm"]["state"] == "FAULT"


def test_cooling_correlation_promotes_weak_signals() -> None:
    engine = OracleEngine()
    _warm_fan_baseline(engine)

    outlook = engine.observe(
        timestamp=20.0,
        metrics={"fan.pwm": 198.0, "fan.rpm": 1350.0},
    )

    assert outlook["metrics"]["fan.pwm"]["state"] == "WATCH"
    assert outlook["metrics"]["fan.rpm"]["state"] == "WATCH"
    assert outlook["state"] == "DEVELOPING"
    assert outlook["correlations"][0]["key"] == "cooling.efficiency"


def test_oracle_has_multiple_cross_signal_hypotheses() -> None:
    keys = {rule.key for rule in DEFAULT_CORRELATIONS}

    assert {
        "cooling.efficiency",
        "chassis.airflow",
        "storage.media",
        "network.path",
    } <= keys


def test_holodeck_fan_degradation_is_seen_before_hard_fault() -> None:
    report = run_oracle_scenario(fan_bearing_degradation())

    assert report["simulation"] is True
    assert report["production_mutation"] is False
    assert report["early_warning"] is True
    assert report["lead_samples"] is not None
    assert report["lead_samples"] >= 20
    assert report["peak_state"] == "FAULT"
    assert "cooling.efficiency" in report["correlations"]


def test_holodeck_drive_degradation_is_seen_before_hard_fault() -> None:
    report = run_oracle_scenario(drive_degradation())

    assert report["early_warning"] is True
    assert report["first_oracle_signal_index"] < report["hard_fault_index"]
    assert report["lead_samples"] >= 10
    assert report["peak_state"] == "FAULT"


def test_holodeck_network_degradation_is_seen_before_hard_fault() -> None:
    report = run_oracle_scenario(network_path_degradation())

    assert report["early_warning"] is True
    assert report["first_oracle_signal_index"] < report["hard_fault_index"]
    assert report["peak_state"] == "FAULT"
    assert "network.path" in report["correlations"]


def test_ghost_mode_projects_redundant_drive_failure_without_mutation() -> None:
    storage = {
        "pools": [{"name": "HDDs", "health": "ONLINE"}],
        "devices": [
            {
                "device": "/dev/sdc",
                "physical_bay": 3,
                "present": True,
                "pool": "HDDs",
                "zfs_state": "ONLINE",
                "remaining_redundancy": 1,
                "mapping_source": "kernel",
            }
        ],
    }

    result = simulate_drive_failure(storage, bay=3)

    assert result["available"] is True
    assert result["simulation"] is True
    assert result["read_only"] is True
    assert result["production_mutation"] is False
    assert result["destructive_actions"] is False
    assert result["current_pool_state"] == "ONLINE"
    assert result["projected_pool_state"] == "DEGRADED"
    assert result["data_availability"] == "AVAILABLE"
    assert result["remaining_redundancy_after"] == 0
    assert "pathfinder.guided_recovery_ready" in result["expected_events"]


def test_ghost_mode_fails_closed_when_drive_identity_is_ambiguous() -> None:
    storage = {
        "pools": [{"name": "HDDs", "health": "ONLINE"}],
        "devices": [
            {"physical_bay": 3, "present": True, "pool": "HDDs"},
            {"physical_bay": 3, "present": True, "pool": "HDDs"},
        ],
    }

    result = simulate_drive_failure(storage, bay=3)

    assert result["available"] is False
    assert result["reason"] == "drive_identity_ambiguous_or_unresolved"
    assert result["production_mutation"] is False
    assert result["destructive_actions"] is False
