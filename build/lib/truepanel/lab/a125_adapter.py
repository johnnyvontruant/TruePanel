"""
A125 execution adapter for Project Stargate.

This adapter supports only cataloged, documented, read-only A125 commands.
It contains no arbitrary opcode path and rejects all payload-bearing requests.
"""

from __future__ import annotations

from dataclasses import dataclass

from .catalog import (
    A125_COMMAND_CATALOG,
    CommandCatalog,
    CommandSafety,
)
from .execution import (
    AdapterResponse,
    ExecutionAdapter,
)


class A125AdapterError(RuntimeError):
    """Base error for A125 adapter validation failures."""


class UnsupportedA125Command(A125AdapterError):
    """Raised when a request is not present in the command catalog."""


class A125CommandMismatch(A125AdapterError):
    """Raised when request metadata does not match the catalog."""


class A125PayloadRejected(A125AdapterError):
    """Raised when a read-only request contains a payload."""


class A125HandlerUnavailable(A125AdapterError):
    """Raised when the controller lacks the cataloged handler."""


@dataclass(frozen=True)
class A125AdapterMetadata:
    command_name: str
    opcode_hex: str
    handler_name: str
    safety: str

    def as_dict(self):
        return {
            "command_name": self.command_name,
            "opcode_hex": self.opcode_hex,
            "handler_name": self.handler_name,
            "safety": self.safety,
            "adapter": "a125",
            "read_only": True,
        }


class A125ExecutionAdapter(ExecutionAdapter):
    """
    Execute approved read-only requests through an A125 controller.

    Validation order is deliberately strict:

    1. Request name must exist in the catalog.
    2. Request opcode must match the catalog.
    3. Catalog entry must be documented read-only.
    4. Request payload must be empty.
    5. Controller handler must exist and be callable.
    """

    def __init__(
        self,
        controller,
        *,
        catalog: CommandCatalog | None = None,
    ):
        if controller is None:
            raise ValueError("controller is required")

        self.controller = controller
        self.catalog = catalog or A125_COMMAND_CATALOG

    def execute(self, request):
        command = self.catalog.get(request.name)

        if command is None:
            raise UnsupportedA125Command(
                f"unsupported A125 command: {request.name}"
            )

        if request.opcode != command.opcode:
            raise A125CommandMismatch(
                (
                    f"opcode mismatch for {request.name}: "
                    f"request=0x{request.opcode:02X}, "
                    f"catalog={command.opcode_hex}"
                )
            )

        if (
            command.safety
            is not CommandSafety.DOCUMENTED_READ_ONLY
            or not command.read_only
        ):
            raise UnsupportedA125Command(
                (
                    f"A125 adapter permits documented "
                    f"read-only commands only: {request.name}"
                )
            )

        if command.payload_allowed:
            raise UnsupportedA125Command(
                (
                    f"catalog command unexpectedly permits payloads: "
                    f"{request.name}"
                )
            )

        if request.payload:
            raise A125PayloadRejected(
                (
                    f"payload rejected for read-only command: "
                    f"{request.name}"
                )
            )

        handler = getattr(
            self.controller,
            command.handler_name,
            None,
        )

        if not callable(handler):
            raise A125HandlerUnavailable(
                (
                    f"controller handler unavailable: "
                    f"{command.handler_name}"
                )
            )

        value = handler()

        metadata = A125AdapterMetadata(
            command_name=command.name,
            opcode_hex=command.opcode_hex,
            handler_name=command.handler_name,
            safety=command.safety.value,
        ).as_dict()

        if isinstance(value, int):
            metadata.update(
                {
                    "value": value,
                    "value_hex": f"0x{value:04X}",
                }
            )

        return AdapterResponse(
            data=value,
            metadata=metadata,
        )
