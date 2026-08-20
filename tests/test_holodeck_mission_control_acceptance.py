from truepanel.holodeck.missions import mission_names
from truepanel.holodeck.report import (
    run_flight_deck_report,
    run_mission_report,
)


def test_each_mission_passes_operator_visible_acceptance(tmp_path):
    for name in mission_names():
        report = run_mission_report(
            name,
            runtime_dir=tmp_path / name,
        )
        acceptance = report["mission_control_acceptance"]

        assert acceptance["passed"] is True
        assert acceptance["check_count"] >= 4
        assert acceptance["failed_count"] == 0
        assert all(item["passed"] for item in acceptance["checks"])


def test_each_mission_passes_temporal_semantics(tmp_path):
    for name in mission_names():
        report = run_mission_report(
            name,
            runtime_dir=tmp_path / f"temporal-{name}",
        )
        temporal = report["temporal_semantics"]

        assert temporal["passed"] is True
        assert temporal["check_count"] >= 4
        assert temporal["failed_count"] == 0
        assert all(item["passed"] for item in temporal["checks"])


def test_fan_stall_is_visible_and_recovers_in_health_model(tmp_path):
    report = run_mission_report(
        "fan-stall-recovery",
        runtime_dir=tmp_path / "fan",
    )
    checks = {
        item["check_id"]: item["passed"]
        for item in report["mission_control_acceptance"]["checks"]
    }

    assert checks["mission_control.cooling_degraded_visible"] is True
    assert checks["mission_control.cooling_recovery_visible"] is True


def test_fan_stall_debounces_once_and_recovers_once(tmp_path):
    report = run_mission_report(
        "fan-stall-recovery",
        runtime_dir=tmp_path / "fan-temporal",
    )
    checks = {
        item["check_id"]: item["passed"]
        for item in report["temporal_semantics"]["checks"]
    }

    assert report["observation_interval_seconds"] == 10.0
    assert report["fan_event_count"] == 2
    assert checks["temporal.fan_debounce_observations_present"] is True
    assert checks["temporal.fan_alert_on_third_failed_observation"] is True
    assert checks["temporal.fan_alert_not_duplicated"] is True
    assert checks["temporal.fan_recovery_emitted_once"] is True


def test_storage_fault_transition_is_not_repeated(tmp_path):
    report = run_mission_report(
        "drive-failure",
        runtime_dir=tmp_path / "drive-failure-temporal",
    )
    checks = {
        item["check_id"]: item["passed"]
        for item in report["temporal_semantics"]["checks"]
    }

    assert report["storage_event_count"] == 1
    assert checks["temporal.storage_fault_transition_once"] is True
    assert checks["temporal.storage_fault_not_duplicated"] is True


def test_storage_removal_transition_is_not_repeated(tmp_path):
    report = run_mission_report(
        "drive-removal",
        runtime_dir=tmp_path / "drive-removal-temporal",
    )
    checks = {
        item["check_id"]: item["passed"]
        for item in report["temporal_semantics"]["checks"]
    }

    assert report["storage_event_count"] == 1
    assert checks["temporal.storage_removal_transition_once"] is True
    assert checks["temporal.storage_removal_not_duplicated"] is True


def test_network_and_front_panel_outages_persist_until_recovery(tmp_path):
    network = run_mission_report(
        "network-flap",
        runtime_dir=tmp_path / "network-temporal",
    )
    lcd = run_mission_report(
        "lcd-loss-recovery",
        runtime_dir=tmp_path / "lcd-temporal",
    )

    network_checks = {
        item["check_id"]: item["passed"]
        for item in network["temporal_semantics"]["checks"]
    }
    lcd_checks = {
        item["check_id"]: item["passed"]
        for item in lcd["temporal_semantics"]["checks"]
    }

    assert network_checks["temporal.network_outage_persists"] is True
    assert network_checks["temporal.network_recovers_at_event"] is True
    assert lcd_checks["temporal.front_panel_outage_persists"] is True
    assert lcd_checks["temporal.front_panel_recovers_at_event"] is True


def test_stale_telemetry_persists_until_recovery_event(tmp_path):
    report = run_mission_report(
        "stale-telemetry-recovery",
        runtime_dir=tmp_path / "stale-temporal",
    )
    checks = {
        item["check_id"]: item["passed"]
        for item in report["temporal_semantics"]["checks"]
    }

    assert checks["temporal.stale_telemetry_persists"] is True
    assert checks["temporal.telemetry_recovers_at_event"] is True


def test_thermal_recommendation_is_visible_through_status_bridge(tmp_path):
    report = run_mission_report(
        "thermal-ramp",
        runtime_dir=tmp_path / "thermal",
    )
    checks = {
        item["check_id"]: item["passed"]
        for item in report["mission_control_acceptance"]["checks"]
    }

    assert checks["mission_control.thermal_afterburners_visible"] is True
    assert checks["mission_control.thermal_downshift_visible"] is True
    assert checks[
        "mission_control.thermal_recommendation_matches_policy"
    ] is True


def test_stale_telemetry_is_visible_and_recovers_in_mission_control(tmp_path):
    report = run_mission_report(
        "stale-telemetry-recovery",
        runtime_dir=tmp_path / "stale",
    )
    checks = {
        item["check_id"]: item["passed"]
        for item in report["mission_control_acceptance"]["checks"]
    }

    assert checks["mission_control.stale_thermal_invalid_visible"] is True
    assert checks["mission_control.stale_thermal_automatic_visible"] is True
    assert checks["mission_control.thermal_validity_recovered"] is True
    assert checks["mission_control.thermal_profile_recovered"] is True


def test_flight_deck_requires_all_mission_control_acceptance(tmp_path):
    report = run_flight_deck_report(runtime_dir=tmp_path / "flight-deck")

    assert report["passed"] is True
    assert report["mission_control_acceptance_passed"] == len(mission_names())
    assert report["temporal_semantics_passed"] == len(mission_names())
    assert all(
        item["mission_control_acceptance_passed"]
        for item in report["missions"]
    )
    assert all(
        item["temporal_semantics_passed"]
        for item in report["missions"]
    )
