import json
from dataclasses import dataclass

import pytest

from truepanel import cli
from truepanel.host import commands


@dataclass
class FakeCheck:
    status: str
    name: str
    detail: str


@dataclass
class FakeReport:
    classification: str
    checks: tuple[FakeCheck, ...]


def fake_report():
    return FakeReport(
        classification="SUPPORTED",
        checks=(
            FakeCheck(
                "PASS",
                "Front Panel Serial",
                "/dev/ttyS1 present",
            ),
            FakeCheck(
                "PASS",
                "Fan Telemetry",
                "fan1_input fan2_input",
            ),
            FakeCheck(
                "PASS",
                "PWM Interfaces",
                "pwm1 pwm2",
            ),
            FakeCheck(
                "PASS",
                "Enclosure Topology",
                "6 slots",
            ),
        ),
    )


def test_parser_accepts_host_capabilities():
    args = cli.build_parser().parse_args(
        [
            "host",
            "capabilities",
        ]
    )

    assert args.command == "host"
    assert args.host_command == "capabilities"
    assert args.host_capabilities_json is False
    assert args.host_capabilities_root is None


def test_parser_accepts_host_capabilities_json():
    args = cli.build_parser().parse_args(
        [
            "host",
            "capabilities",
            "--json",
        ]
    )

    assert args.host_capabilities_json is True


def test_parser_accepts_host_capabilities_root():
    args = cli.build_parser().parse_args(
        [
            "host",
            "capabilities",
            "--root",
            "/tmp/host-root",
        ]
    )

    assert (
        args.host_capabilities_root
        == "/tmp/host-root"
    )


def test_host_capabilities_human_output(
    monkeypatch,
    capsys,
):
    monkeypatch.setattr(
        commands,
        "collect_compatibility",
        lambda **kwargs: fake_report(),
    )

    result = commands.run_host_capabilities()

    output = capsys.readouterr().out

    assert result == 0
    assert "TruePanel Host Agent Capabilities" in output
    assert "Platform" in output
    assert "LCD" in output
    assert "Fan Telemetry" in output
    assert "Fan Control" in output
    assert "Enclosure" in output
    assert "Hardware authority: LOCKED" in output
    assert "Fan Control" in output
    assert "[LOCKED]" in output


def test_host_capabilities_json_output(
    monkeypatch,
    capsys,
):
    monkeypatch.setattr(
        commands,
        "collect_compatibility",
        lambda **kwargs: fake_report(),
    )

    result = commands.run_host_capabilities(
        json_output=True
    )

    payload = json.loads(
        capsys.readouterr().out
    )

    assert result == 0
    assert payload["host_agent"] == {
        "available": True,
        "hardware_authority_granted": False,
    }

    assert (
        payload["capabilities"]["fan_control"][
            "available"
        ]
        is True
    )

    assert (
        payload["capabilities"]["fan_control"][
            "authorized"
        ]
        is False
    )


def test_host_capabilities_passes_root_to_survey(
    monkeypatch,
    tmp_path,
):
    captured = {}

    def collect(**kwargs):
        captured.update(kwargs)
        return fake_report()

    monkeypatch.setattr(
        commands,
        "collect_compatibility",
        collect,
    )

    commands.run_host_capabilities(
        root=tmp_path
    )

    assert captured == {
        "root": tmp_path
    }


def test_cli_dispatches_host_before_plugins(
    monkeypatch,
):
    monkeypatch.setattr(
        cli.sys,
        "argv",
        [
            "truepanel",
            "host",
            "capabilities",
        ],
    )

    monkeypatch.setattr(
        cli,
        "handle_host_command",
        lambda args: 9,
    )

    def fail_plugin_load():
        raise AssertionError(
            "host command must not load plugins"
        )

    monkeypatch.setattr(
        cli,
        "load_plugins",
        fail_plugin_load,
    )

    with pytest.raises(SystemExit) as error:
        cli.main()

    assert error.value.code == 9
