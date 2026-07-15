import pytest

from truepanel.lab.catalog import (
    CommandCatalog,
    CommandCategory,
    CommandSafety,
    LabCommand,
)
from truepanel.lab.interlock import (
    DangerLevel,
    ExecutionMode,
)
from truepanel.lab.request_factory import (
    A125_REQUEST_FACTORY,
    CatalogPayloadRejected,
    CatalogRequestFactory,
    RequestBuildResult,
    UnknownCatalogCommand,
    build_a125_request_factory,
)


def test_a125_factory_builds_board_request():
    request = A125_REQUEST_FACTORY.build(
        "board-query"
    )

    assert request.name == "board-query"
    assert request.opcode == 0x00
    assert request.mode is ExecutionMode.SIMULATION
    assert request.danger_level is DangerLevel.SAFE
    assert request.known_opcode is True
    assert (
        request.expected_controller_family
        == "A125"
    )
    assert request.payload == b""


def test_a125_factory_builds_button_request():
    request = A125_REQUEST_FACTORY.build(
        "button-query",
        mode=ExecutionMode.LIVE,
    )

    assert request.opcode == 0x06
    assert request.mode is ExecutionMode.LIVE


def test_a125_factory_builds_version_request():
    request = A125_REQUEST_FACTORY.build(
        "version-query"
    )

    assert request.opcode == 0x07
    assert (
        request.danger_level
        is DangerLevel.SAFE
    )


def test_unknown_command_rejected():
    with pytest.raises(
        UnknownCatalogCommand,
        match="unknown catalog command",
    ):
        A125_REQUEST_FACTORY.build(
            "reactor-overload"
        )


def test_read_only_payload_rejected():
    with pytest.raises(
        CatalogPayloadRejected,
        match="payload is not permitted",
    ):
        A125_REQUEST_FACTORY.build(
            "board-query",
            payload=b"\x01",
        )


def test_mode_must_be_execution_mode():
    with pytest.raises(
        TypeError,
        match="mode must be an ExecutionMode",
    ):
        A125_REQUEST_FACTORY.build(
            "board-query",
            mode="live",
        )


def test_payload_must_be_bytes():
    with pytest.raises(
        TypeError,
        match="payload must be bytes",
    ):
        A125_REQUEST_FACTORY.build(
            "board-query",
            payload="not-bytes",
        )


def test_factory_requires_catalog():
    with pytest.raises(
        TypeError,
        match="catalog must be a CommandCatalog",
    ):
        CatalogRequestFactory(
            object(),
            controller_family="A125",
        )


def test_factory_requires_controller_family():
    with pytest.raises(
        ValueError,
        match="controller_family is required",
    ):
        CatalogRequestFactory(
            CommandCatalog(),
            controller_family="",
        )


def test_factory_uses_catalog_danger_level():
    command = LabCommand(
        name="danger-test",
        opcode=0x20,
        category=CommandCategory.CONTROL,
        safety=CommandSafety.DANGEROUS,
        danger_level=DangerLevel.DANGEROUS,
        handler_name="danger_test",
        description="Synthetic dangerous command.",
        documented=True,
        read_only=False,
        payload_allowed=False,
    )
    factory = CatalogRequestFactory(
        CommandCatalog([command]),
        controller_family="TEST",
    )

    request = factory.build(
        "danger-test",
        mode=ExecutionMode.LIVE,
    )

    assert (
        request.danger_level
        is DangerLevel.DANGEROUS
    )
    assert request.opcode == 0x20
    assert request.known_opcode is True
    assert (
        request.expected_controller_family
        == "TEST"
    )


def test_factory_uses_requires_live_flag():
    command = LabCommand(
        name="live-test",
        opcode=0x21,
        category=CommandCategory.DIAGNOSTIC,
        safety=CommandSafety.DOCUMENTED_READ_ONLY,
        danger_level=DangerLevel.SAFE,
        handler_name="live_test",
        description="Synthetic live-only command.",
        documented=True,
        read_only=True,
        requires_live_hardware=True,
    )
    factory = CatalogRequestFactory(
        CommandCatalog([command]),
        controller_family="TEST",
    )

    request = factory.build(
        "live-test"
    )

    assert request.requires_live_hardware is True


def test_payload_allowed_for_write_command():
    command = LabCommand(
        name="write-test",
        opcode=0x22,
        category=CommandCategory.DISPLAY,
        safety=CommandSafety.DOCUMENTED_WRITE,
        danger_level=DangerLevel.DANGEROUS,
        handler_name="write_test",
        description="Synthetic payload command.",
        documented=True,
        read_only=False,
        payload_allowed=True,
    )
    factory = CatalogRequestFactory(
        CommandCatalog([command]),
        controller_family="TEST",
    )

    request = factory.build(
        "write-test",
        payload=b"\xAA\x55",
    )

    assert request.payload == b"\xAA\x55"


def test_build_result_preserves_command_definition():
    result = A125_REQUEST_FACTORY.build_result(
        "board-query",
        mode=ExecutionMode.LIVE,
    )

    assert isinstance(result, RequestBuildResult)
    assert result.request.name == "board-query"
    assert result.command.name == "board-query"
    assert result.command.opcode == result.request.opcode


def test_build_result_serializes():
    result = A125_REQUEST_FACTORY.build_result(
        "version-query"
    )

    payload = result.as_dict()

    assert (
        payload["request"]["name"]
        == "version-query"
    )
    assert (
        payload["request"]["opcode_hex"]
        == "0x07"
    )
    assert (
        payload["request"]["known_opcode"]
        is True
    )
    assert (
        payload["command"]["safety"]
        == "documented_read_only"
    )


def test_factory_returns_unique_request_ids():
    first = A125_REQUEST_FACTORY.build(
        "board-query"
    )
    second = A125_REQUEST_FACTORY.build(
        "board-query"
    )

    assert first.request_id != second.request_id


def test_a125_factory_builder_returns_fresh_factory():
    first = build_a125_request_factory()
    second = build_a125_request_factory()

    assert first is not second
    assert first.catalog is second.catalog
    assert (
        first.controller_family
        == second.controller_family
        == "A125"
    )
