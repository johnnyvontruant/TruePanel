"""
Catalog-bound execution request construction.

Callers must not manually assert whether an opcode is known or safe. This
factory derives execution metadata from a validated CommandCatalog.
"""

from __future__ import annotations

from dataclasses import dataclass

from .catalog import (
    A125_COMMAND_CATALOG,
    CommandCatalog,
    LabCommand,
)
from .interlock import (
    ExecutionMode,
    ExecutionRequest,
)


class RequestFactoryError(ValueError):
    """Base error for catalog-bound request creation."""


class UnknownCatalogCommand(RequestFactoryError):
    """Raised when a requested command is absent from the catalog."""


class CatalogPayloadRejected(RequestFactoryError):
    """Raised when payload policy does not permit supplied data."""


@dataclass(frozen=True)
class RequestBuildResult:
    """
    Request and canonical command definition used to build it.
    """

    request: ExecutionRequest
    command: LabCommand

    def as_dict(self):
        return {
            "request": {
                "request_id": self.request.request_id,
                "name": self.request.name,
                "opcode": self.request.opcode,
                "opcode_hex": (
                    f"0x{self.request.opcode:02X}"
                ),
                "mode": self.request.mode.value,
                "danger_level": (
                    self.request.danger_level.value
                ),
                "known_opcode": (
                    self.request.known_opcode
                ),
                "requires_live_hardware": (
                    self.request.requires_live_hardware
                ),
                "expected_controller_family": (
                    self.request.expected_controller_family
                ),
                "payload_hex": (
                    self.request.payload.hex()
                ),
            },
            "command": self.command.as_dict(),
        }


class CatalogRequestFactory:
    """
    Construct ExecutionRequest objects from canonical catalog definitions.
    """

    def __init__(
        self,
        catalog: CommandCatalog,
        *,
        controller_family: str,
    ):
        if not isinstance(catalog, CommandCatalog):
            raise TypeError(
                "catalog must be a CommandCatalog"
            )

        if (
            not controller_family
            or not controller_family.strip()
        ):
            raise ValueError(
                "controller_family is required"
            )

        self.catalog = catalog
        self.controller_family = (
            controller_family.strip()
        )

    def build(
        self,
        command_name,
        *,
        mode=ExecutionMode.SIMULATION,
        payload=b"",
    ):
        if not isinstance(mode, ExecutionMode):
            raise TypeError(
                "mode must be an ExecutionMode"
            )

        if not isinstance(payload, bytes):
            raise TypeError(
                "payload must be bytes"
            )

        command = self.catalog.get(command_name)

        if command is None:
            raise UnknownCatalogCommand(
                (
                    "unknown catalog command: "
                    f"{command_name}"
                )
            )

        self._validate_payload(
            command,
            payload,
        )

        request = ExecutionRequest(
            opcode=command.opcode,
            name=command.name,
            payload=payload,
            danger_level=command.danger_level,
            mode=mode,
            expected_controller_family=(
                self.controller_family
            ),
            known_opcode=True,
            requires_live_hardware=(
                command.requires_live_hardware
            ),
        )

        return request

    def build_result(
        self,
        command_name,
        *,
        mode=ExecutionMode.SIMULATION,
        payload=b"",
    ):
        request = self.build(
            command_name,
            mode=mode,
            payload=payload,
        )

        return RequestBuildResult(
            request=request,
            command=self.catalog.require(
                command_name
            ),
        )

    @staticmethod
    def _validate_payload(
        command,
        payload,
    ):
        if payload and not command.payload_allowed:
            raise CatalogPayloadRejected(
                (
                    "payload is not permitted for "
                    f"{command.name}"
                )
            )

        if command.read_only and payload:
            raise CatalogPayloadRejected(
                (
                    "read-only command cannot carry "
                    f"a payload: {command.name}"
                )
            )


def build_a125_request_factory():
    """
    Return the canonical request factory for confirmed A125 commands.
    """

    return CatalogRequestFactory(
        A125_COMMAND_CATALOG,
        controller_family="A125",
    )


A125_REQUEST_FACTORY = build_a125_request_factory()
