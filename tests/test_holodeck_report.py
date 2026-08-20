from truepanel.holodeck.missions import mission_names
from truepanel.holodeck.report import (
    DEFAULT_OBSERVATION_INTERVAL_SECONDS,
    run_mission_report,
)


def test_each_builtin_mission_produces_a_bounded_flight_report(tmp_path):
    for name in mission_names():
        report = run_mission_report(
            name,
            runtime_dir=tmp_path / name,
        )

        assert report["mission"] == name
        assert report["host"] == "battlestation"
        assert report["scenario_event_count"] >= 2

        cadence_ticks = int(
            report["simulated_seconds"]
            // DEFAULT_OBSERVATION_INTERVAL_SECONDS
        )
        maximum_observations = (
            cadence_ticks
            + report["scenario_event_count"]
            + 1
        )

        assert report["observation_count"] >= report["scenario_event_count"] + 1
        assert report["observation_count"] <= maximum_observations
        assert report["invariants"]["rule_count"] > 0
        assert "snapshot" not in report
        assert "hostname" not in report


def test_thermal_ramp_report_records_recovered_terminal_temperature(tmp_path):
    report = run_mission_report(
        "thermal-ramp",
        runtime_dir=tmp_path / "thermal",
    )

    assert report["simulated_seconds"] == 300
    assert report["scenario_event_count"] == 5
    assert report["final"]["cpu_temperature_c"] == 54.0
    assert report["final"]["telemetry_fresh"] is True


def test_drive_failure_report_records_degraded_pool(tmp_path):
    report = run_mission_report(
        "drive-failure",
        runtime_dir=tmp_path / "drive",
    )

    assert report["simulated_seconds"] == 35
    assert report["final"]["pool_health"]["HDDs"] == "DEGRADED"


def test_recovery_missions_finish_recovered(tmp_path):
    network = run_mission_report(
        "network-flap",
        runtime_dir=tmp_path / "network",
    )
    lcd = run_mission_report(
        "lcd-loss-recovery",
        runtime_dir=tmp_path / "lcd",
    )
    telemetry = run_mission_report(
        "stale-telemetry-recovery",
        runtime_dir=tmp_path / "telemetry",
    )

    assert network["final"]["primary_network_up"] is True
    assert lcd["final"]["lcd_connected"] is True
    assert telemetry["final"]["telemetry_fresh"] is True
