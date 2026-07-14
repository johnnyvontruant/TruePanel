import json
from contextlib import contextmanager
from pathlib import Path

from truepanel.lab.commands import (
    build_parser,
    main,
    run_capabilities,
)


class FakeController:
    def query_board_id(self):
        return 0x007D

    def query_protocol_version(self):
        return 0x0003

    def query_buttons(self):
        return 0x0000


@contextmanager
def fake_open_controller(*args, **kwargs):
    yield FakeController(), Path(
        "development/logs/fake_capabilities.log"
    )


def test_parser_accepts_capabilities_command():
    args = build_parser().parse_args(["capabilities"])

    assert args.lab_command == "capabilities"
    assert args.handler is run_capabilities
    assert args.live is False
    assert args.compact is False


def test_parser_accepts_live_capabilities_json():
    args = build_parser().parse_args(
        ["capabilities", "--live", "--json"]
    )

    assert args.live is True
    assert args.json_output is True


def test_baseline_capabilities_do_not_open_hardware(
    monkeypatch,
):
    def fail_if_called(*args, **kwargs):
        raise AssertionError("hardware should not be opened")

    monkeypatch.setattr(
        "truepanel.lab.commands.open_controller",
        fail_if_called,
    )

    args = build_parser().parse_args(["capabilities"])
    result = run_capabilities(args)

    assert result.success is True
    assert result.data["supported"] == 3
    assert result.capture_path == ""


def test_live_capabilities_use_hardware_provider(
    monkeypatch,
):
    monkeypatch.setattr(
        "truepanel.lab.commands.open_controller",
        fake_open_controller,
    )

    args = build_parser().parse_args(
        ["capabilities", "--live"]
    )
    result = run_capabilities(args)

    assert result.success is True
    assert result.data["supported"] == 3
    assert result.data["result_count"] == 3
    assert result.capture_path.endswith(
        "fake_capabilities.log"
    )


def test_main_prints_live_capability_report(
    monkeypatch,
    capsys,
):
    monkeypatch.setattr(
        "truepanel.lab.commands.open_controller",
        fake_open_controller,
    )

    exit_code = main(["capabilities", "--live"])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "Project Stargate Capability Report" in output
    assert "[+] Board Query" in output
    assert "[+] Version Query" in output
    assert "[+] Button Query" in output


def test_main_prints_live_capabilities_json(
    monkeypatch,
    capsys,
):
    monkeypatch.setattr(
        "truepanel.lab.commands.open_controller",
        fake_open_controller,
    )

    exit_code = main(
        ["capabilities", "--live", "--json"]
    )
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["supported"] == 3
    assert payload["provider_count"] == 1
    assert (
        payload["providers"][0]["provider"]
        == "a125_identity"
    )


def test_main_prints_compact_capability_json(
    monkeypatch,
    capsys,
):
    monkeypatch.setattr(
        "truepanel.lab.commands.open_controller",
        fake_open_controller,
    )

    exit_code = main(
        ["capabilities", "--live", "--compact"]
    )
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "\n" not in output.rstrip("\n")
    assert json.loads(output)["supported"] == 3
