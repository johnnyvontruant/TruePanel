import argparse

from truepanel.hardware.commands import (
    COMMAND_HANDLERS,
    COMMAND_REGISTRARS,
    add_hardware_subcommands,
)


def build_parser():
    parser = argparse.ArgumentParser()
    subcommands = parser.add_subparsers(dest="command")
    add_hardware_subcommands(subcommands)
    return parser


def test_builtin_hardware_commands_are_registered():
    parser = build_parser()

    storage = parser.parse_args(["hardware", "storage"])
    topology = parser.parse_args(["hardware", "topology"])
    health = parser.parse_args(["hardware", "health"])

    assert storage.hardware_action == "storage"
    assert topology.hardware_action == "topology"
    assert health.hardware_action == "health"


def test_builtin_registry_has_matching_handlers():
    assert len(COMMAND_REGISTRARS) == 3
    assert len(COMMAND_HANDLERS) == 3


def test_health_parser_uses_shared_destinations():
    parser = build_parser()

    args = parser.parse_args(
        [
            "hardware",
            "health",
            "--verbose",
            "--json",
            "--device",
            "sda",
        ]
    )

    assert args.hardware_action == "health"
    assert args.hardware_verbose is True
    assert args.hardware_json is True
    assert args.device == "sda"


def test_health_selectors_are_mutually_exclusive():
    parser = build_parser()

    try:
        parser.parse_args(
            [
                "hardware",
                "health",
                "--device",
                "sda",
                "--bay",
                "1",
            ]
        )
    except SystemExit as exc:
        assert exc.code == 2
    else:
        raise AssertionError(
            "health selectors should be mutually exclusive"
        )
