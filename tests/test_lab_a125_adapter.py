import pytest

from truepanel.lab.a125_adapter import (
    A125CommandMismatch,
    A125ExecutionAdapter,
    A125HandlerUnavailable,
    A125PayloadRejected,
    UnsupportedA125Command,
)
from truepanel.lab.catalog import (
    CommandCatalog,
    CommandCategory,
    CommandSafety,
    LabCommand,
)
from truepanel.lab.execution import AdapterResponse
from truepanel.lab.interlock import (
    DangerLevel,
    ExecutionMode,
    ExecutionRequest,
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


def make_request(
    *,
    name="board-query",
    opcode=0x00,
    payload=b"",
):
    return ExecutionRequest(
        name=name,
        opcode=opcode,
        payload=payload,
        danger_level=DangerLevel.SAFE,
        mode=ExecutionMode.LIVE,
        known_opcode=True,
    )


def test_board_query_calls_controller():
    controller = FakeController()
    adapter = A125ExecutionAdapter(controller)

    response = adapter.execute(
        make_request()
    )

    assert isinstance(response, AdapterResponse)
    assert response.data == 0x007D
    assert controller.calls == ["board"]


def test_button_query_calls_controller():
    controller = FakeController()
    adapter = A125ExecutionAdapter(controller)

    response = adapter.execute(
        make_request(
            name="button-query",
            opcode=0x06,
        )
    )

    assert response.data == 0x0010
    assert controller.calls == ["buttons"]


def test_version_query_calls_controller():
    controller = FakeController()
    adapter = A125ExecutionAdapter(controller)

    response = adapter.execute(
        make_request(
            name="version-query",
            opcode=0x07,
        )
    )

    assert response.data == 0x0003
    assert controller.calls == ["version"]


def test_response_contains_catalog_metadata():
    adapter = A125ExecutionAdapter(
        FakeController()
    )

    response = adapter.execute(
        make_request()
    )

    assert response.metadata == {
        "command_name": "board-query",
        "opcode_hex": "0x00",
        "handler_name": "query_board_id",
        "safety": "documented_read_only",
        "adapter": "a125",
        "read_only": True,
        "value": 0x007D,
        "value_hex": "0x007D",
    }


def test_unknown_command_rejected_before_controller_call():
    controller = FakeController()
    adapter = A125ExecutionAdapter(controller)

    with pytest.raises(
        UnsupportedA125Command,
        match="unsupported A125 command",
    ):
        adapter.execute(
            make_request(
                name="reset",
                opcode=0xFF,
            )
        )

    assert controller.calls == []


def test_opcode_mismatch_rejected():
    controller = FakeController()
    adapter = A125ExecutionAdapter(controller)

    with pytest.raises(
        A125CommandMismatch,
        match="opcode mismatch",
    ):
        adapter.execute(
            make_request(
                name="board-query",
                opcode=0x06,
            )
        )

    assert controller.calls == []


def test_payload_rejected():
    controller = FakeController()
    adapter = A125ExecutionAdapter(controller)

    with pytest.raises(
        A125PayloadRejected,
        match="payload rejected",
    ):
        adapter.execute(
            make_request(
                payload=b"\x01",
            )
        )

    assert controller.calls == []


def test_missing_handler_rejected():
    class IncompleteController:
        pass

    adapter = A125ExecutionAdapter(
        IncompleteController()
    )

    with pytest.raises(
        A125HandlerUnavailable,
        match="controller handler unavailable",
    ):
        adapter.execute(
            make_request()
        )


def test_controller_is_required():
    with pytest.raises(
        ValueError,
        match="controller is required",
    ):
        A125ExecutionAdapter(None)


def test_custom_catalog_is_supported():
    controller = FakeController()

    command = LabCommand(
        name="custom-board-query",
        opcode=0x20,
        category=CommandCategory.IDENTITY,
        safety=CommandSafety.DOCUMENTED_READ_ONLY,
        danger_level=DangerLevel.SAFE,
        handler_name="query_board_id",
        description="Read board ID through a custom catalog.",
        documented=True,
        read_only=True,
    )

    adapter = A125ExecutionAdapter(
        controller,
        catalog=CommandCatalog([command]),
    )

    response = adapter.execute(
        make_request(
            name="custom-board-query",
            opcode=0x20,
        )
    )

    assert response.data == 0x007D
    assert controller.calls == ["board"]


def test_non_read_only_catalog_entry_rejected():
    controller = FakeController()

    command = LabCommand(
        name="display-write",
        opcode=0x0C,
        category=CommandCategory.DISPLAY,
        safety=CommandSafety.DOCUMENTED_WRITE,
        danger_level=DangerLevel.DANGEROUS,
        handler_name="query_board_id",
        description="Synthetic write command.",
        documented=True,
        read_only=False,
        payload_allowed=True,
    )

    adapter = A125ExecutionAdapter(
        controller,
        catalog=CommandCatalog([command]),
    )

    with pytest.raises(
        UnsupportedA125Command,
        match="documented read-only commands only",
    ):
        adapter.execute(
            make_request(
                name="display-write",
                opcode=0x0C,
            )
        )

    assert controller.calls == []
