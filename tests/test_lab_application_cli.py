import pytest

from truepanel.lab.application import (
    LaboratoryApplicationConfiguration,
    build_a125_laboratory_application,
)
from truepanel.lab.application_cli import (
    ApplicationCommandResult,
    LaboratoryApplicationCLI,
    format_command_catalog,
    format_execution_result,
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


def build_application():
    CONTROLLER.calls.clear()

    return build_a125_laboratory_application(
        CONTROLLER,
        configuration=(
            LaboratoryApplicationConfiguration(
                cooldown_seconds=0,
            )
        ),
    )


def test_bridge_requires_application_factory():
    with pytest.raises(
        TypeError,
        match="application_factory must be callable",
    ):
        LaboratoryApplicationCLI(object())


def test_factory_must_return_application():
    bridge = LaboratoryApplicationCLI(
        lambda: object()
    )

    with pytest.raises(
        TypeError,
        match="must return a LaboratoryApplication",
    ):
        bridge.commands()


def test_commands_returns_catalog_payload():
    bridge = LaboratoryApplicationCLI(
        build_application
    )

    result = bridge.commands()

    assert isinstance(
        result,
        ApplicationCommandResult,
    )
    assert result.success is True
    assert result.command == "commands"
    assert result.value == 3
    assert result.data["controller_family"] == "A125"
    assert result.data["command_count"] == 3
    assert tuple(
        command["name"]
        for command in result.data["commands"]
    ) == (
        "board-query",
        "button-query",
        "version-query",
    )


def test_execute_defaults_to_simulation():
    bridge = LaboratoryApplicationCLI(
        build_application
    )

    result = bridge.execute(
        "board-query"
    )

    assert result.success is True
    assert result.command == "execute-board-query"
    assert result.data["status"] == "simulated"
    assert result.data["opcode_hex"] == "0x00"
    assert CONTROLLER.calls == []


def test_execute_live_uses_application():
    bridge = LaboratoryApplicationCLI(
        build_application
    )

    result = bridge.execute(
        "version-query",
        live=True,
    )

    assert result.success is True
    assert result.value == 0x0003
    assert result.data["status"] == "succeeded"
    assert (
        result.data["metadata"]["value_hex"]
        == "0x0003"
    )
    assert CONTROLLER.calls == ["version"]


def test_execute_requires_command_name():
    bridge = LaboratoryApplicationCLI(
        build_application
    )

    with pytest.raises(
        ValueError,
        match="command_name is required",
    ):
        bridge.execute("")


def test_live_must_be_boolean():
    bridge = LaboratoryApplicationCLI(
        build_application
    )

    with pytest.raises(
        TypeError,
        match="live must be a boolean",
    ):
        bridge.execute(
            "board-query",
            live="yes",
        )


def test_result_serializes():
    bridge = LaboratoryApplicationCLI(
        build_application
    )

    payload = bridge.execute(
        "button-query"
    ).as_dict()

    assert payload["command"] == (
        "execute-button-query"
    )
    assert payload["success"] is True
    assert payload["data"]["status"] == (
        "simulated"
    )


def test_catalog_formatter():
    bridge = LaboratoryApplicationCLI(
        build_application
    )

    output = format_command_catalog(
        bridge.commands()
    )

    assert (
        "Project Stargate Command Catalog"
        in output
    )
    assert "Controller : A125" in output
    assert "0x00  board-query" in output
    assert "0x06  button-query" in output
    assert "0x07  version-query" in output
    assert "documented_read_only" in output


def test_execution_formatter_simulation():
    bridge = LaboratoryApplicationCLI(
        build_application
    )

    output = format_execution_result(
        bridge.execute(
            "board-query"
        )
    )

    assert "Project Stargate Execution" in output
    assert "Command  : board-query" in output
    assert "Opcode   : 0x00" in output
    assert "Status   : SIMULATED" in output
    assert "Decision : simulation_allowed" in output


def test_execution_formatter_live_value():
    bridge = LaboratoryApplicationCLI(
        build_application
    )

    output = format_execution_result(
        bridge.execute(
            "board-query",
            live=True,
        )
    )

    assert "Status   : SUCCEEDED" in output
    assert "Value    : 0x007D" in output
    assert CONTROLLER.calls == ["board"]


def test_formatters_require_bridge_result():
    with pytest.raises(
        TypeError,
        match="ApplicationCommandResult",
    ):
        format_command_catalog(object())

    with pytest.raises(
        TypeError,
        match="ApplicationCommandResult",
    ):
        format_execution_result(object())
