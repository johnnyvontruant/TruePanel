from pathlib import Path

from truepanel.config.loader import (
    DEFAULT_CONFIG,
    load_config,
)
from truepanel.mission_control.watchers.fan_health import (
    build_fan_health_watcher,
)


def test_default_config_enables_fan_health():
    settings = DEFAULT_CONFIG[
        "mission_control"
    ]["fan_health"]

    assert settings["enabled"] is True
    assert settings["interval"] == 10
    assert settings["minimum_rpm"] == 300
    assert settings["consecutive_failures"] == 3
    assert (
        settings["emit_initial_conditions"]
        is False
    )


def test_project_yaml_loads_fan_health():
    config = load_config(
        "truepanel.yaml"
    )
    settings = config[
        "mission_control"
    ]["fan_health"]

    assert settings["enabled"] is True
    assert settings["interval"] == 10
    assert settings["minimum_rpm"] == 300
    assert settings[
        "consecutive_failures"
    ] == 3

    channels = config[
        "hardware"
    ]["fans"]["channels"]

    fan3 = (
        channels.get(3)
        or channels.get("3")
    )

    assert fan3["monitored"] is False


def test_runtime_launcher_registers_watcher():
    source = Path(
        "lcd-menu.py"
    ).read_text(
        encoding="utf-8"
    )

    assert (
        "build_fan_health_watcher(config)"
        in source
    )
    assert (
        "mission.register(fan_health_watcher)"
        in source
    )


def test_factory_reads_project_config():
    config = load_config(
        "truepanel.yaml"
    )

    watcher = build_fan_health_watcher(
        config,
        status_provider=lambda: {
            "fan_channels": [],
        },
    )

    assert watcher is not None
    assert watcher.channels[1][
        "monitored"
    ] is True
    assert watcher.channels[3][
        "monitored"
    ] is False
