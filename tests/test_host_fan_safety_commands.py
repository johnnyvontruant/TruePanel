import argparse
import json

import truepanel.host.commands as commands
from truepanel.host.fan_safety import (
    FanAutomaticCheck,
    HostFanSafetyReport,
)


def safe_report():
    return HostFanSafetyReport(
        fan_control_enabled=True,
        controller_path="/sys/class/hwmon/hwmon10/device",
        checks=(
            FanAutomaticCheck(
                channel=1,
                path=(
                    "/sys/class/hwmon/hwmon10/device/"
                    "pwm1_enable"
                ),
                mode=2,
                automatic=True,
                detail="Motherboard Automatic mode confirmed.",
            ),
        ),
        reason=(
            "All configured fan-control channels are in motherboard "
            "Automatic mode."
        ),
    )


def unsafe_report():
    return HostFanSafetyReport(
        fan_control_enabled=True,
        controller_path="/sys/class/hwmon/hwmon10/device",
        checks=(
            FanAutomaticCheck(
                channel=1,
                path=(
                    "/sys/class/hwmon/hwmon10/device/"
                    "pwm1_enable"
                ),
                mode=1,
                automatic=False,
                detail="Expected motherboard Automatic mode 2.",
            ),
        ),
        reason="Automatic mode is not confirmed.",
    )


def test_host_parser_registers_fan_safety_command():
    parser = argparse.ArgumentParser()
    subcommands = parser.add_subparsers(
        dest="command"
    )
    commands.add_host_subcommands(subcommands)

    args = parser.parse_args(
        [
            "host",
            "fan-safety",
            "--config",
            "/opt/truepanel/truepanel.yaml",
            "--json",
        ]
    )

    assert args.command == "host"
    assert args.host_command == "fan-safety"
    assert args.host_fan_safety_config == (
        "/opt/truepanel/truepanel.yaml"
    )
    assert args.host_fan_safety_json is True


def test_fan_safety_command_outputs_json_and_success(
    monkeypatch,
    capsys,
):
    monkeypatch.setattr(
        commands,
        "load_config",
        lambda path: {"config": path},
    )
    monkeypatch.setattr(
        commands,
        "collect_host_fan_safety",
        lambda config: safe_report(),
    )

    result = commands.run_host_fan_safety(
        json_output=True,
        config_path="/tmp/truepanel.yaml",
    )
    payload = json.loads(
        capsys.readouterr().out
    )

    assert result == 0
    assert payload["safe"] is True
    assert payload["checks"][0]["mode"] == 2


def test_fan_safety_command_returns_review_when_not_automatic(
    monkeypatch,
    capsys,
):
    monkeypatch.setattr(
        commands,
        "load_config",
        lambda path: {},
    )
    monkeypatch.setattr(
        commands,
        "collect_host_fan_safety",
        lambda config: unsafe_report(),
    )

    result = commands.run_host_fan_safety(
        json_output=False,
    )
    output = capsys.readouterr().out

    assert result == 1
    assert "Motherboard fan control: REVIEW" in output


def test_host_dispatch_routes_fan_safety(
    monkeypatch,
    capsys,
):
    monkeypatch.setattr(
        commands,
        "load_config",
        lambda path: {},
    )
    monkeypatch.setattr(
        commands,
        "collect_host_fan_safety",
        lambda config: safe_report(),
    )

    args = argparse.Namespace(
        command="host",
        host_command="fan-safety",
        host_fan_safety_config="truepanel.yaml",
        host_fan_safety_json=True,
    )

    result = commands.handle_host_command(args)
    payload = json.loads(
        capsys.readouterr().out
    )

    assert result == 0
    assert payload["safe"] is True
