import json
from contextlib import contextmanager
from pathlib import Path

from truepanel.lab.commands import (
    build_parser,
    main,
    run_board,
    run_buttons,
    run_version,
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
        return 0x0010


CONTROLLER = FakeController()


@contextmanager
def fake_open_controller(
    command,
    port,
    baud,
    timeout,
    capture_dir,
):
    CONTROLLER.calls.clear()

    yield CONTROLLER, Path(
        f"development/logs/fake_{command}.log"
    )


def test_board_uses_application_pipeline(
    monkeypatch,
):
    monkeypatch.setattr(
        "truepanel.lab.commands.open_controller",
        fake_open_controller,
    )

    args = build_parser().parse_args(
        ["board"]
    )

    result = run_board(args)

    assert result.success is True
    assert result.command == "board"
    assert result.value == "0x007D"
    assert result.detail == (
        "Live execution allowed"
    )
    assert result.capture_path.endswith(
        "fake_board.log"
    )
    assert result.data["catalog_command"] == (
        "board-query"
    )
    assert result.data["opcode_hex"] == "0x00"
    assert result.data["status"] == "succeeded"
    assert result.data["decision"] == "allowed"
    assert (
        result.data["metadata"]["adapter"]
        == "a125"
    )
    assert CONTROLLER.calls == ["board"]


def test_version_uses_application_pipeline(
    monkeypatch,
):
    monkeypatch.setattr(
        "truepanel.lab.commands.open_controller",
        fake_open_controller,
    )

    args = build_parser().parse_args(
        ["version"]
    )

    result = run_version(args)

    assert result.success is True
    assert result.value == "0x0003"
    assert result.data["catalog_command"] == (
        "version-query"
    )
    assert result.data["opcode_hex"] == "0x07"
    assert CONTROLLER.calls == ["version"]


def test_buttons_uses_application_pipeline(
    monkeypatch,
):
    monkeypatch.setattr(
        "truepanel.lab.commands.open_controller",
        fake_open_controller,
    )

    args = build_parser().parse_args(
        ["buttons"]
    )

    result = run_buttons(args)

    assert result.success is True
    assert result.value == "0x0010"
    assert result.data["catalog_command"] == (
        "button-query"
    )
    assert result.data["opcode_hex"] == "0x06"
    assert CONTROLLER.calls == ["buttons"]


def test_main_preserves_human_output(
    monkeypatch,
    capsys,
):
    monkeypatch.setattr(
        "truepanel.lab.commands.open_controller",
        fake_open_controller,
    )

    exit_code = main(["board"])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "Command: board" in output
    assert "Status: PASS" in output
    assert "Value: 0x007D" in output
    assert "Detail: Live execution allowed" in output
    assert "fake_board.log" in output


def test_main_preserves_json_output(
    monkeypatch,
    capsys,
):
    monkeypatch.setattr(
        "truepanel.lab.commands.open_controller",
        fake_open_controller,
    )

    exit_code = main(
        ["--json", "version"]
    )

    payload = json.loads(
        capsys.readouterr().out
    )

    assert exit_code == 0
    assert payload["command"] == "version"
    assert payload["success"] is True
    assert payload["value"] == "0x0003"
    assert (
        payload["data"]["catalog_command"]
        == "version-query"
    )
    assert (
        payload["data"]["metadata"]["value_hex"]
        == "0x0003"
    )


def test_each_command_opens_controller_once(
    monkeypatch,
):
    openings = []

    @contextmanager
    def tracking_open_controller(
        command,
        port,
        baud,
        timeout,
        capture_dir,
    ):
        openings.append(command)
        yield CONTROLLER, Path(
            f"{command}.log"
        )

    monkeypatch.setattr(
        "truepanel.lab.commands.open_controller",
        tracking_open_controller,
    )

    main(["board"])
    main(["version"])
    main(["buttons"])

    assert openings == [
        "board",
        "version",
        "buttons",
    ]
