import json
from contextlib import contextmanager
from pathlib import Path

import pytest

from truepanel.lab.commands import (
    build_parser,
    main,
    run_fingerprint,
)


class FakeController:
    def __init__(self):
        self.calls = []

    def query_board_id(self):
        self.calls.append("board")
        return 0x007D

    def query_protocol_version(self):
        self.calls.append("version")
        return 0x0003

    def query_buttons(self):
        self.calls.append("buttons")
        return 0x0000


CONTROLLER = FakeController()


@contextmanager
def fake_open_controller(*args, **kwargs):
    CONTROLLER.calls.clear()

    yield CONTROLLER, Path(
        "development/logs/fake_fingerprint.log"
    )


def test_parser_accepts_live_fingerprint():
    args = build_parser().parse_args(
        ["fingerprint", "--live"]
    )

    assert args.lab_command == "fingerprint"
    assert args.live is True


def test_baseline_fingerprint_does_not_open_hardware(
    monkeypatch,
):
    def fail_if_called(*args, **kwargs):
        raise AssertionError("hardware should not be opened")

    monkeypatch.setattr(
        "truepanel.lab.commands.open_controller",
        fail_if_called,
    )

    args = build_parser().parse_args(["fingerprint"])
    result = run_fingerprint(args)

    assert result.success is True
    assert result.data["board_id"] is None
    assert (
        result.data["metadata"].get("acquisition_mode")
        != "live"
    )


def test_live_fingerprint_uses_provider_pipeline(
    monkeypatch,
):
    monkeypatch.setattr(
        "truepanel.lab.commands.open_controller",
        fake_open_controller,
    )

    args = build_parser().parse_args(
        ["fingerprint", "--live", "--json"]
    )
    result = run_fingerprint(args)

    assert result.success is True
    assert result.data["board_id"] == "0x007D"
    assert result.data["firmware_version"] == "0x0003"
    assert (
        result.data["timing"]["average_latency_ms"]
        is not None
    )
    assert result.data["confidence"] == pytest.approx(1.0)


def test_live_fingerprint_queries_each_operation_once(
    monkeypatch,
):
    monkeypatch.setattr(
        "truepanel.lab.commands.open_controller",
        fake_open_controller,
    )

    args = build_parser().parse_args(
        ["fingerprint", "--live"]
    )
    run_fingerprint(args)

    assert CONTROLLER.calls == [
        "board",
        "buttons",
        "version",
    ]


def test_live_fingerprint_records_capability_report(
    monkeypatch,
):
    monkeypatch.setattr(
        "truepanel.lab.commands.open_controller",
        fake_open_controller,
    )

    args = build_parser().parse_args(
        ["fingerprint", "--live"]
    )
    result = run_fingerprint(args)
    metadata = result.data["metadata"]

    assert metadata["acquisition_mode"] == "live"
    assert metadata["capability_provider_count"] == 1
    assert metadata["capability_result_count"] == 3
    assert metadata["capability_supported"] == 3

    capability_report = metadata["capability_report"]

    assert capability_report["provider_count"] == 1
    assert capability_report["supported"] == 3


def test_main_outputs_live_json(
    monkeypatch,
    capsys,
):
    monkeypatch.setattr(
        "truepanel.lab.commands.open_controller",
        fake_open_controller,
    )

    exit_code = main(
        ["fingerprint", "--live", "--json"]
    )
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["board_id"] == "0x007D"
    assert payload["firmware_version"] == "0x0003"
    assert payload["metadata"]["acquisition_mode"] == "live"
    assert (
        payload["capabilities"]["board_query"]["confidence"]
        == 1.0
    )


def test_main_outputs_live_human_fingerprint(
    monkeypatch,
    capsys,
):
    monkeypatch.setattr(
        "truepanel.lab.commands.open_controller",
        fake_open_controller,
    )

    exit_code = main(["fingerprint", "--live"])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "Board ID   : 0x007D" in output
    assert "Firmware   : 0x0003" in output
    assert "Latency    :" in output
    assert "Confidence : 100.0%" in output
