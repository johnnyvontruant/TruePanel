"""
Project Stargate command catalog.

The catalog is the canonical source of truth for laboratory command metadata.
It describes commands but never executes them and never communicates with
hardware.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Iterable

from .interlock import DangerLevel


class CommandCategory(Enum):
    IDENTITY = "identity"
    INPUT = "input"
    DISPLAY = "display"
    CONTROL = "control"
    DIAGNOSTIC = "diagnostic"
    UNKNOWN = "unknown"


class CommandSafety(Enum):
    DOCUMENTED_READ_ONLY = "documented_read_only"
    DOCUMENTED_WRITE = "documented_write"
    EXPERIMENTAL = "experimental"
    DANGEROUS = "dangerous"
    FORBIDDEN = "forbidden"


@dataclass(frozen=True)
class LabCommand:
    """
    Canonical definition of one laboratory command.

    handler_name identifies the controller method used by an adapter. The
    catalog stores the method name rather than a bound callable so definitions
    remain controller-neutral and serializable.
    """

    name: str
    opcode: int
    category: CommandCategory
    safety: CommandSafety
    danger_level: DangerLevel
    handler_name: str
    description: str
    documented: bool = True
    read_only: bool = True
    requires_live_hardware: bool = False
    payload_allowed: bool = False

    def __post_init__(self):
        if not self.name or not self.name.strip():
            raise ValueError("command name is required")

        if self.name != self.name.strip():
            raise ValueError(
                "command name cannot contain surrounding whitespace"
            )

        if not isinstance(self.opcode, int):
            raise TypeError("opcode must be an integer")

        if not 0 <= self.opcode <= 0xFF:
            raise ValueError(
                "opcode must be between 0x00 and 0xFF"
            )

        if not isinstance(self.category, CommandCategory):
            raise TypeError(
                "category must be a CommandCategory"
            )

        if not isinstance(self.safety, CommandSafety):
            raise TypeError(
                "safety must be a CommandSafety"
            )

        if not isinstance(self.danger_level, DangerLevel):
            raise TypeError(
                "danger_level must be a DangerLevel"
            )

        if not self.handler_name or not self.handler_name.strip():
            raise ValueError("handler_name is required")

        if not self.description or not self.description.strip():
            raise ValueError("description is required")

        if self.read_only and self.payload_allowed:
            raise ValueError(
                "read-only commands cannot accept payloads"
            )

        if (
            self.safety
            is CommandSafety.DOCUMENTED_READ_ONLY
            and not self.read_only
        ):
            raise ValueError(
                "documented read-only commands must be read-only"
            )

        if (
            self.safety is CommandSafety.FORBIDDEN
            and self.danger_level is not DangerLevel.FORBIDDEN
        ):
            raise ValueError(
                "forbidden commands must use forbidden danger level"
            )

    @property
    def opcode_hex(self):
        return f"0x{self.opcode:02X}"

    def as_dict(self):
        return {
            "name": self.name,
            "opcode": self.opcode,
            "opcode_hex": self.opcode_hex,
            "category": self.category.value,
            "safety": self.safety.value,
            "danger_level": self.danger_level.value,
            "handler_name": self.handler_name,
            "description": self.description,
            "documented": self.documented,
            "read_only": self.read_only,
            "requires_live_hardware": (
                self.requires_live_hardware
            ),
            "payload_allowed": self.payload_allowed,
        }


class CommandCatalog:
    """
    Validated registry of laboratory command definitions.

    Names and opcodes must both be unique. Catalog queries never return mutable
    internal structures.
    """

    def __init__(
        self,
        commands: Iterable[LabCommand] = (),
    ):
        self._by_name = {}
        self._by_opcode = {}

        for command in commands:
            self.register(command)

    def register(self, command):
        if not isinstance(command, LabCommand):
            raise TypeError(
                "command must be a LabCommand"
            )

        if command.name in self._by_name:
            raise ValueError(
                f"duplicate command name: {command.name}"
            )

        if command.opcode in self._by_opcode:
            existing = self._by_opcode[command.opcode]

            raise ValueError(
                "duplicate command opcode "
                f"{command.opcode_hex}: "
                f"{existing.name} and {command.name}"
            )

        self._by_name[command.name] = command
        self._by_opcode[command.opcode] = command

        return command

    def get(self, name):
        return self._by_name.get(name)

    def require(self, name):
        command = self.get(name)

        if command is None:
            raise KeyError(
                f"unknown laboratory command: {name}"
            )

        return command

    def get_opcode(self, opcode):
        return self._by_opcode.get(opcode)

    def require_opcode(self, opcode):
        command = self.get_opcode(opcode)

        if command is None:
            raise KeyError(
                "unknown laboratory opcode: "
                f"0x{opcode:02X}"
            )

        return command

    def contains_name(self, name):
        return name in self._by_name

    def contains_opcode(self, opcode):
        return opcode in self._by_opcode

    def is_known_opcode(self, opcode):
        return self.contains_opcode(opcode)

    def commands(self):
        return tuple(
            sorted(
                self._by_name.values(),
                key=lambda command: (
                    command.opcode,
                    command.name,
                ),
            )
        )

    def names(self):
        return tuple(
            command.name
            for command in self.commands()
        )

    def opcodes(self):
        return tuple(
            command.opcode
            for command in self.commands()
        )

    def documented_commands(self):
        return tuple(
            command
            for command in self.commands()
            if command.documented
        )

    def read_only_commands(self):
        return tuple(
            command
            for command in self.commands()
            if command.read_only
        )

    def experimental_commands(self):
        return tuple(
            command
            for command in self.commands()
            if (
                command.safety
                is CommandSafety.EXPERIMENTAL
            )
        )

    def commands_by_category(self, category):
        if not isinstance(category, CommandCategory):
            raise TypeError(
                "category must be a CommandCategory"
            )

        return tuple(
            command
            for command in self.commands()
            if command.category is category
        )

    def unknown_opcodes(
        self,
        *,
        start=0x00,
        end=0xFF,
    ):
        if not isinstance(start, int) or not isinstance(end, int):
            raise TypeError(
                "opcode range values must be integers"
            )

        if not 0 <= start <= 0xFF:
            raise ValueError(
                "start must be between 0x00 and 0xFF"
            )

        if not 0 <= end <= 0xFF:
            raise ValueError(
                "end must be between 0x00 and 0xFF"
            )

        if start > end:
            raise ValueError(
                "start cannot be greater than end"
            )

        return tuple(
            opcode
            for opcode in range(start, end + 1)
            if opcode not in self._by_opcode
        )

    def as_dict(self):
        return {
            "command_count": len(self),
            "commands": [
                command.as_dict()
                for command in self.commands()
            ],
        }

    @property
    def by_name(self):
        return MappingProxyType(
            dict(self._by_name)
        )

    @property
    def by_opcode(self):
        return MappingProxyType(
            dict(self._by_opcode)
        )

    def __contains__(self, item):
        if isinstance(item, str):
            return self.contains_name(item)

        if isinstance(item, int):
            return self.contains_opcode(item)

        return False

    def __iter__(self):
        return iter(self.commands())

    def __len__(self):
        return len(self._by_name)


A125_BOARD_QUERY = LabCommand(
    name="board-query",
    opcode=0x00,
    category=CommandCategory.IDENTITY,
    safety=CommandSafety.DOCUMENTED_READ_ONLY,
    danger_level=DangerLevel.SAFE,
    handler_name="query_board_id",
    description="Read the A125 controller board identifier.",
    documented=True,
    read_only=True,
)

A125_BUTTON_QUERY = LabCommand(
    name="button-query",
    opcode=0x06,
    category=CommandCategory.INPUT,
    safety=CommandSafety.DOCUMENTED_READ_ONLY,
    danger_level=DangerLevel.SAFE,
    handler_name="query_buttons",
    description="Read the current A125 front-panel button state.",
    documented=True,
    read_only=True,
)

A125_VERSION_QUERY = LabCommand(
    name="version-query",
    opcode=0x07,
    category=CommandCategory.IDENTITY,
    safety=CommandSafety.DOCUMENTED_READ_ONLY,
    danger_level=DangerLevel.SAFE,
    handler_name="query_protocol_version",
    description="Read the A125 protocol version.",
    documented=True,
    read_only=True,
)


def build_a125_command_catalog():
    """
    Return a fresh catalog containing only confirmed A125 read-only commands.
    """

    return CommandCatalog(
        (
            A125_BOARD_QUERY,
            A125_BUTTON_QUERY,
            A125_VERSION_QUERY,
        )
    )


A125_COMMAND_CATALOG = build_a125_command_catalog()
