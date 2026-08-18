import json

import pytest

from truepanel.cli import build_parser
from truepanel.history.black_box import BlackBoxFrame, BlackBoxRecorder
from truepanel.holodeck.commands import handle_holodeck_command


def test_holodeck_run_parser_and_handler(capsys):
    args = build_parser().parse_args(
        ["holodeck", "run", "battlestation", "--steps", "2", "--json"]
    )
    assert handle_holodeck_command(args) == 0
    lines = capsys.readouterr().out.splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["system"]["hostname"] == "HoloDeck-BattleStation"


def test_holodeck_inject_cli(capsys):
    args = build_parser().parse_args(
        ["holodeck", "inject", "fan_stall", "channel=1"]
    )
    assert handle_holodeck_command(args) == 0
    state = json.loads(capsys.readouterr().out)
    assert state["fans"]["fan_channels"][0]["rpm"] == 0


def test_holodeck_replays_black_box_through_mission_control(tmp_path, capsys):
    path = tmp_path / "incident.jsonl"
    recorder = BlackBoxRecorder(path)
    recorder.append(
        BlackBoxFrame.capture(
            captured_at=10,
            sequence=1,
            storage={"pool_health": "ONLINE"},
        )
    )
    recorder.append(
        BlackBoxFrame.capture(
            captured_at=20,
            sequence=2,
            storage={"pool_health": "DEGRADED"},
        )
    )
    args = build_parser().parse_args(
        ["holodeck", "replay", str(path), "--json"]
    )
    assert handle_holodeck_command(args) == 0
    payloads = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert [item["health"]["subsystems"]["storage"]["state"] for item in payloads] == [
        "NOMINAL",
        "DEGRADED",
    ]


def test_holodeck_check_emits_compact_bounded_report(capsys):
    args = build_parser().parse_args(
        ["holodeck", "check", "battlestation", "--steps", "2", "--json"]
    )

    assert handle_holodeck_command(args) == 0
    report = json.loads(capsys.readouterr().out)

    assert report == {
        "observation_count": 2,
        "passed": True,
        "rule_count": 4,
        "violation_count": 0,
        "violations": [],
    }
    assert "hostname" not in report
    assert "snapshot" not in report


@pytest.mark.parametrize(
    "action",
    (
        "run",
        "check",
    ),
)
def test_holodeck_commands_reject_unbounded_steps(
    action,
):
    with pytest.raises(
        (SystemExit, ValueError),
    ):
        build_parser().parse_args(
            [
                "holodeck",
                action,
                "--steps",
                "1001",
            ]
        )


@pytest.mark.parametrize(
    "action",
    (
        "run",
        "check",
    ),
)
@pytest.mark.parametrize(
    "value",
    (
        "nan",
        "inf",
        "-inf",
        "-1",
    ),
)
def test_holodeck_commands_reject_invalid_step_interval(
    action,
    value,
):
    with pytest.raises(
        (SystemExit, ValueError),
    ):
        build_parser().parse_args(
            [
                "holodeck",
                action,
                "--step-seconds",
                value,
            ]
        )


def test_compile_incident_writes_sanitized_data_and_prints_manifest(
    tmp_path,
    capsys,
):
    recording = tmp_path / "incident.jsonl"
    output = tmp_path / "compiled.json"
    recorder = BlackBoxRecorder(recording)
    recorder.append(
        BlackBoxFrame.capture(
            captured_at=10,
            sequence=1,
            fan={
                "fan_channels": [
                    {
                        "number": 1,
                        "rpm": 0,
                        "stalled": True,
                        "healthy": True,
                        "alarm": False,
                    }
                ]
            },
            telemetry={"hostname": "private-host"},
        )
    )
    args = build_parser().parse_args(
        [
            "holodeck",
            "compile-incident",
            str(recording),
            "--invariant",
            "cooling.stalled_not_healthy",
            "--output",
            str(output),
        ]
    )

    assert handle_holodeck_command(args) == 0
    manifest = json.loads(capsys.readouterr().out)
    artifact = json.loads(output.read_text())

    assert manifest == artifact["manifest"]
    assert manifest["minimized_frame_count"] == 1
    assert manifest["executable_code_generated"] is False
    assert artifact["scenario"]["frames"][0]["telemetry"]["hostname"] == (
        "<redacted>"
    )


def test_compile_incident_refuses_to_overwrite_output(tmp_path):
    recording = tmp_path / "incident.jsonl"
    output = tmp_path / "compiled.json"
    output.write_text("owned by operator")
    BlackBoxRecorder(recording).append(
        BlackBoxFrame.capture(captured_at=10, sequence=1)
    )
    args = build_parser().parse_args(
        [
            "holodeck",
            "compile-incident",
            str(recording),
            "--invariant",
            "holodeck.hardware_isolated",
            "--output",
            str(output),
        ]
    )

    with pytest.raises(ValueError, match="refusing to overwrite"):
        handle_holodeck_command(args)

    assert output.read_text() == "owned by operator"
