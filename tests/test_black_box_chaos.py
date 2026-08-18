from truepanel.history.black_box import BlackBoxFrame
from truepanel.history.black_box_chaos import (
    SUPPORTED_CHAOS_FAULTS,
    BlackBoxChaosFault,
    BlackBoxChaosScenario,
    inject_chaos_fault,
)


def base_frame():
    return BlackBoxFrame.capture(
        captured_at=10.0,
        sequence=7,
        lcd={"page": "show_pool_health", "stale": False},
        fan={"healthy": True, "rpm": 1500},
        storage={"health": "ONLINE"},
        mission_control={"available": True},
    )


def test_supported_fault_catalog_is_explicit_and_bounded():
    assert {
        "fan_stall",
        "storage_degraded",
        "lcd_stale",
        "mission_control_unavailable",
    } == SUPPORTED_CHAOS_FAULTS


def test_fan_stall_is_data_only_and_does_not_mutate_recording():
    frame = base_frame()

    injected = inject_chaos_fault(
        frame,
        BlackBoxChaosFault("fan_stall"),
    )

    assert frame.fan == {"healthy": True, "rpm": 1500}
    assert injected.fan["healthy"] is False
    assert injected.fan["rpm"] == 0
    assert injected.fan["simulated_fault"] == "fan_stall"
    assert injected.sequence == frame.sequence
    assert injected.captured_at == frame.captured_at
    assert injected.alerts[-1]["simulated"] is True


def test_each_fault_changes_only_its_owned_projection():
    frame = base_frame()

    storage = inject_chaos_fault(
        frame,
        BlackBoxChaosFault("storage_degraded"),
    )
    assert storage.storage["health"] == "DEGRADED"
    assert storage.fan == frame.fan

    lcd = inject_chaos_fault(
        frame,
        BlackBoxChaosFault("lcd_stale"),
    )
    assert lcd.lcd["stale"] is True
    assert lcd.storage == frame.storage

    mission = inject_chaos_fault(
        frame,
        BlackBoxChaosFault("mission_control_unavailable"),
    )
    assert mission.mission_control["available"] is False
    assert mission.lcd == frame.lcd


def test_fault_details_pass_through_black_box_privacy_sanitizer():
    injected = inject_chaos_fault(
        base_frame(),
        BlackBoxChaosFault(
            "storage_degraded",
            {
                "hostname": "secret-nas",
                "message": "failed peer 192.168.0.42",
            },
        ),
    )

    details = injected.alerts[-1]["details"]
    assert details["hostname"] == "<redacted>"
    assert "192.168.0.42" not in details["message"]
    assert "<redacted>" in details["message"]


def test_scenario_applies_only_to_selected_sequence():
    frame = base_frame()
    other = BlackBoxFrame.capture(captured_at=11.0, sequence=8)
    scenario = BlackBoxChaosScenario(
        {7: BlackBoxChaosFault("lcd_stale")}
    )

    assert scenario.apply(frame).lcd["stale"] is True
    assert scenario.apply(other) is other


def test_invalid_faults_and_scenarios_fail_closed():
    try:
        BlackBoxChaosFault("shell_command")
    except ValueError as error:
        assert "unsupported" in str(error)
    else:
        raise AssertionError("unknown chaos fault was accepted")

    try:
        BlackBoxChaosScenario({-1: BlackBoxChaosFault("lcd_stale")})
    except ValueError as error:
        assert "non-negative" in str(error)
    else:
        raise AssertionError("negative scenario sequence was accepted")

    try:
        inject_chaos_fault(object(), BlackBoxChaosFault("lcd_stale"))
    except TypeError as error:
        assert "BlackBoxFrame" in str(error)
    else:
        raise AssertionError("non-frame chaos target was accepted")
