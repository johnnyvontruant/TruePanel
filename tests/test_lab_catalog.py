import pytest

from truepanel.lab.catalog import (
    A125_BOARD_QUERY,
    A125_BUTTON_QUERY,
    A125_COMMAND_CATALOG,
    A125_VERSION_QUERY,
    CommandCatalog,
    CommandCategory,
    CommandSafety,
    LabCommand,
    build_a125_command_catalog,
)
from truepanel.lab.interlock import DangerLevel


def make_command(
    *,
    name="test-query",
    opcode=0x10,
    category=CommandCategory.DIAGNOSTIC,
    safety=CommandSafety.DOCUMENTED_READ_ONLY,
    danger_level=DangerLevel.SAFE,
    handler_name="query_test",
    description="Read a test value.",
    documented=True,
    read_only=True,
    requires_live_hardware=False,
    payload_allowed=False,
):
    return LabCommand(
        name=name,
        opcode=opcode,
        category=category,
        safety=safety,
        danger_level=danger_level,
        handler_name=handler_name,
        description=description,
        documented=documented,
        read_only=read_only,
        requires_live_hardware=(
            requires_live_hardware
        ),
        payload_allowed=payload_allowed,
    )


def test_initial_a125_catalog_contains_three_commands():
    assert len(A125_COMMAND_CATALOG) == 3

    assert A125_COMMAND_CATALOG.names() == (
        "board-query",
        "button-query",
        "version-query",
    )


def test_initial_a125_opcodes_are_confirmed_values():
    assert A125_COMMAND_CATALOG.opcodes() == (
        0x00,
        0x06,
        0x07,
    )


def test_board_query_definition():
    command = A125_COMMAND_CATALOG.require(
        "board-query"
    )

    assert command is A125_BOARD_QUERY
    assert command.opcode == 0x00
    assert command.opcode_hex == "0x00"
    assert command.handler_name == "query_board_id"
    assert command.category is CommandCategory.IDENTITY
    assert (
        command.safety
        is CommandSafety.DOCUMENTED_READ_ONLY
    )
    assert command.danger_level is DangerLevel.SAFE
    assert command.read_only is True
    assert command.payload_allowed is False


def test_button_query_definition():
    command = A125_COMMAND_CATALOG.require(
        "button-query"
    )

    assert command is A125_BUTTON_QUERY
    assert command.opcode == 0x06
    assert command.handler_name == "query_buttons"
    assert command.category is CommandCategory.INPUT


def test_version_query_definition():
    command = A125_COMMAND_CATALOG.require(
        "version-query"
    )

    assert command is A125_VERSION_QUERY
    assert command.opcode == 0x07
    assert (
        command.handler_name
        == "query_protocol_version"
    )


def test_lookup_by_opcode():
    command = A125_COMMAND_CATALOG.require_opcode(
        0x06
    )

    assert command.name == "button-query"


def test_unknown_name_returns_none():
    assert (
        A125_COMMAND_CATALOG.get("missing")
        is None
    )


def test_unknown_opcode_returns_none():
    assert (
        A125_COMMAND_CATALOG.get_opcode(0x99)
        is None
    )


def test_require_unknown_name_raises():
    with pytest.raises(
        KeyError,
        match="unknown laboratory command",
    ):
        A125_COMMAND_CATALOG.require("missing")


def test_require_unknown_opcode_raises():
    with pytest.raises(
        KeyError,
        match="unknown laboratory opcode",
    ):
        A125_COMMAND_CATALOG.require_opcode(0x99)


def test_duplicate_name_rejected():
    catalog = CommandCatalog(
        [make_command()]
    )

    duplicate = make_command(
        opcode=0x11,
    )

    with pytest.raises(
        ValueError,
        match="duplicate command name",
    ):
        catalog.register(duplicate)


def test_duplicate_opcode_rejected():
    catalog = CommandCatalog(
        [make_command()]
    )

    duplicate = make_command(
        name="other-query",
    )

    with pytest.raises(
        ValueError,
        match="duplicate command opcode",
    ):
        catalog.register(duplicate)


def test_registration_requires_command():
    catalog = CommandCatalog()

    with pytest.raises(
        TypeError,
        match="must be a LabCommand",
    ):
        catalog.register(object())


def test_commands_are_sorted_by_opcode():
    catalog = CommandCatalog(
        [
            make_command(
                name="later",
                opcode=0x20,
            ),
            make_command(
                name="earlier",
                opcode=0x02,
            ),
        ]
    )

    assert catalog.names() == (
        "earlier",
        "later",
    )


def test_documented_filter():
    catalog = CommandCatalog(
        [
            make_command(),
            make_command(
                name="undocumented",
                opcode=0x11,
                documented=False,
            ),
        ]
    )

    assert tuple(
        command.name
        for command in catalog.documented_commands()
    ) == (
        "test-query",
    )


def test_read_only_filter():
    catalog = CommandCatalog(
        [
            make_command(),
            make_command(
                name="write-test",
                opcode=0x11,
                safety=CommandSafety.DOCUMENTED_WRITE,
                danger_level=DangerLevel.DANGEROUS,
                handler_name="write_test",
                description="Write a test value.",
                read_only=False,
                payload_allowed=True,
            ),
        ]
    )

    assert tuple(
        command.name
        for command in catalog.read_only_commands()
    ) == (
        "test-query",
    )


def test_experimental_filter():
    catalog = CommandCatalog(
        [
            make_command(),
            make_command(
                name="experimental-test",
                opcode=0x11,
                safety=CommandSafety.EXPERIMENTAL,
                danger_level=DangerLevel.EXPERIMENTAL,
                documented=False,
            ),
        ]
    )

    assert tuple(
        command.name
        for command in catalog.experimental_commands()
    ) == (
        "experimental-test",
    )


def test_category_filter():
    commands = A125_COMMAND_CATALOG.commands_by_category(
        CommandCategory.IDENTITY
    )

    assert tuple(
        command.name
        for command in commands
    ) == (
        "board-query",
        "version-query",
    )


def test_unknown_opcode_range():
    unknown = A125_COMMAND_CATALOG.unknown_opcodes(
        start=0x00,
        end=0x08,
    )

    assert unknown == (
        0x01,
        0x02,
        0x03,
        0x04,
        0x05,
        0x08,
    )


def test_unknown_opcode_range_rejects_reverse_range():
    with pytest.raises(
        ValueError,
        match="start cannot be greater",
    ):
        A125_COMMAND_CATALOG.unknown_opcodes(
            start=0x10,
            end=0x00,
        )


def test_catalog_membership():
    assert "board-query" in A125_COMMAND_CATALOG
    assert 0x00 in A125_COMMAND_CATALOG
    assert "missing" not in A125_COMMAND_CATALOG
    assert 0x99 not in A125_COMMAND_CATALOG


def test_catalog_iteration():
    assert tuple(A125_COMMAND_CATALOG) == (
        A125_BOARD_QUERY,
        A125_BUTTON_QUERY,
        A125_VERSION_QUERY,
    )


def test_catalog_serialization():
    payload = A125_COMMAND_CATALOG.as_dict()

    assert payload["command_count"] == 3
    assert payload["commands"][0]["name"] == (
        "board-query"
    )
    assert payload["commands"][0]["opcode_hex"] == (
        "0x00"
    )
    assert (
        payload["commands"][0]["safety"]
        == "documented_read_only"
    )


def test_catalog_views_are_read_only():
    by_name = A125_COMMAND_CATALOG.by_name
    by_opcode = A125_COMMAND_CATALOG.by_opcode

    with pytest.raises(TypeError):
        by_name["new"] = make_command()

    with pytest.raises(TypeError):
        by_opcode[0x20] = make_command()


def test_factory_returns_fresh_catalog():
    first = build_a125_command_catalog()
    second = build_a125_command_catalog()

    assert first is not second
    assert first.commands() == second.commands()


def test_command_name_is_required():
    with pytest.raises(
        ValueError,
        match="command name is required",
    ):
        make_command(name="")


def test_opcode_must_be_byte():
    with pytest.raises(
        ValueError,
        match="between 0x00 and 0xFF",
    ):
        make_command(opcode=0x100)


def test_handler_name_is_required():
    with pytest.raises(
        ValueError,
        match="handler_name is required",
    ):
        make_command(handler_name="")


def test_description_is_required():
    with pytest.raises(
        ValueError,
        match="description is required",
    ):
        make_command(description="")


def test_read_only_command_rejects_payload():
    with pytest.raises(
        ValueError,
        match="read-only commands cannot accept payloads",
    ):
        make_command(payload_allowed=True)


def test_forbidden_safety_requires_forbidden_danger():
    with pytest.raises(
        ValueError,
        match="must use forbidden danger level",
    ):
        make_command(
            safety=CommandSafety.FORBIDDEN,
            danger_level=DangerLevel.DANGEROUS,
        )
