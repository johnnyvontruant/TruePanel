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
    assert all(
        item["mission_control_acceptance_passed"]
        for item in report["missions"]
    )
