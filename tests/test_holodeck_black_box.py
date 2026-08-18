from truepanel.history.black_box import BlackBoxFrame, BlackBoxReplay
from truepanel.holodeck import BlackBoxHoloDeckProvider, SimulationSafetyError
from truepanel.web.snapshot import SnapshotService


def replay():
    return BlackBoxReplay(
        (
            BlackBoxFrame.capture(
                captured_at=100,
                sequence=1,
                telemetry={"cpu_percent": 20, "ram_percent": 40},
                fan={"rpm": [1500, 1450]},
                storage={"pool_health": "ONLINE"},
                lcd={"connected": True, "line1": "Mission Ready"},
            ),
            BlackBoxFrame.capture(
                captured_at=110,
                sequence=2,
                telemetry={"cpu_percent": 95, "telemetry_fresh": False},
                fan={"rpm": [0, 1440], "healthy": False},
                storage={"pool_health": "DEGRADED"},
                lcd={"connected": False, "stale": True},
                alerts=[{"severity": "warning", "kind": "fan_stall"}],
            ),
        )
    )


def test_black_box_replay_projects_a_stateful_holodeck_host():
    provider = BlackBoxHoloDeckProvider(replay())

    first = provider.update()
    assert first["black_box"]["sequence"] == 1
    assert first["fans"]["fan_channels"][0]["rpm"] == 1500

    second = provider.step()
    assert second["black_box"]["sequence"] == 2
    assert second["fans"]["fan_channels"][0]["rpm"] == 0
    assert second["pools"][0]["health"] == "DEGRADED"
    assert second["lcd"]["connected"] is False
    assert provider.clock() == 110


def test_black_box_projection_drives_real_mission_control_health(tmp_path):
    provider = BlackBoxHoloDeckProvider(replay())
    service = SnapshotService(
        collector=provider,
        config={},
        history_path=tmp_path / "history.jsonl",
        fan_control_status_path=tmp_path / "fan-status.json",
        lcd_reader_status_path=tmp_path / "lcd-reader.json",
        lcd_display_status_path=tmp_path / "lcd-display.json",
        fan_control_history_path=tmp_path / "fan-history.jsonl",
        thermal_observer_history_path=tmp_path / "thermal-history.jsonl",
        thermal_commissioning_history_path=tmp_path / "commissioning.jsonl",
        fan_status_provider=lambda: provider.update()["fans"],
        clock=provider.clock,
    )

    assert service.status()["health"]["subsystems"]["storage"]["state"] == "NOMINAL"
    provider.step()
    payload = service.status()
    assert payload["health"]["subsystems"]["storage"]["state"] == "DEGRADED"
    assert payload["fans"]["channels"][0]["rpm"] == 0


def test_black_box_holodeck_remains_hardware_isolated():
    provider = BlackBoxHoloDeckProvider(replay())
    try:
        provider.hardware.write("/sys/class/hwmon/hwmon0/pwm1", "255")
    except SimulationSafetyError:
        pass
    else:
        raise AssertionError("Black Box replay reached a hardware writer")


def test_catalog_callers_cannot_mutate_later_twins():
    from truepanel.holodeck.catalog import host_fixture

    first = host_fixture("battlestation")
    first["hostname"] = "mutated"
    assert host_fixture("battlestation")["hostname"] == "HoloDeck-BattleStation"


def test_replay_ignores_reserved_wrong_shaped_telemetry():
    source = BlackBoxReplay(
        (
            BlackBoxFrame.capture(
                captured_at=1,
                sequence=1,
                telemetry={"fans": "broken", "lcd": [], "pools": "broken"},
            ),
        )
    )
    state = BlackBoxHoloDeckProvider(source).update()
    assert isinstance(state["fans"], dict)
    assert isinstance(state["lcd"], dict)
    assert isinstance(state["pools"], list)
