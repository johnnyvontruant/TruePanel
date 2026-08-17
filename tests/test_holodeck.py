import json
from pathlib import Path

import pytest

from truepanel.holodeck import (
    DeterministicClock,
    HoloDeckHostProvider,
    SimulationSafetyError,
    load_scenario,
)
from truepanel.web.snapshot import SnapshotService

FIXTURES = Path(__file__).parent / "fixtures"


def build_provider():
    scenario = load_scenario(
        FIXTURES / "scenarios" / "everything-is-on-fire.yaml"
    )
    return HoloDeckHostProvider.from_path(
        FIXTURES / "hosts" / scenario.host / "host.json",
        scenario=scenario,
        clock=DeterministicClock(0),
    )


def test_scenario_is_deterministic_and_stateful():
    provider = build_provider()

    assert provider.update()["cpu_temperature_c"] == 51.0
    assert provider.advance(20)["fans"]["fan_channels"][0]["rpm"] == 0
    state = provider.advance(20)
    assert state["enclosure"]["bays"][3]["health"] == "FAULTED"
    assert state["network"]["enp116s0"]["link_up"] is False
    assert [event.type for event in provider.applied_events] == [
        "temperature",
        "fan_stall",
        "disk_fault",
        "network_down",
    ]


def test_holodeck_hardware_boundary_is_fail_closed():
    provider = build_provider()

    for operation in (provider.hardware.open, provider.hardware.write, provider.hardware.run):
        with pytest.raises(SimulationSafetyError):
            operation("/dev/ttyS1")

    with pytest.raises(SimulationSafetyError):
        provider.hardware.set_pwm(1, 255)


def test_real_mission_control_snapshot_uses_twin_providers(tmp_path):
    provider = build_provider()
    service = SnapshotService(
        collector=provider,
        config={"hardware": {"fans": {"channels": {"1": {"label": "Rear 1"}}}}},
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

    payload = service.status()
    assert payload["system"]["hostname"] == "HoloDeck-BattleStation"
    assert payload["network"][1]["name"] == "enp116s0"
    assert payload["fans"]["channels"][0]["label"] == "Rear 1"
    json.dumps(payload)


def test_fixture_is_sanitized_and_simulation_only():
    text = (FIXTURES / "hosts" / "battlestation" / "host.json").read_text()
    assert "192.168." not in text
    assert "/dev/" not in text
    assert json.loads(text)["simulation"] is True


def test_clock_rejects_time_travel():
    clock = DeterministicClock(10)
    with pytest.raises(ValueError):
        clock.advance(-1)


def test_provider_reset_rewinds_scenario_clock_and_events():
    provider = build_provider()
    provider.advance(70)
    assert provider.applied_events

    provider.reset()

    assert provider.clock() == 0
    assert provider.applied_events == []
    assert provider.update()["cpu_temperature_c"] == 51.0
