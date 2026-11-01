"""
CLI bridge for the Project Stargate laboratory application.

This module converts argparse-style command inputs into application calls and
normalizes application results for the existing LabResult presentation layer.

It contains no argument parser construction and opens no hardware directly.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .application import LaboratoryApplication
from .execution import ExecutionResult


@dataclass(frozen=True)
class ApplicationCommandResult:
    """
    Presentation-neutral result returned to the existing CLI layer.
    """

    command: str
    success: bool
    value: object = None
    data: dict | None = None
    message: str = ""
    capture_path: str = ""
    error: str = ""

    def as_dict(self):
        return {
            "command": self.command,
            "success": self.success,
            "value": self.value,
            "data": self.data or {},
            "message": self.message,
            "capture_path": self.capture_path,
            "error": self.error,
        }


class LaboratoryApplicationCLI:
    """
    Thin command adapter around LaboratoryApplication.

    The CLI bridge does not assemble interlocks, adapters, catalogs, or
    controllers. Those responsibilities remain inside the application.
    """

    def __init__(
        self,
        application_factory: Callable[
            [],
            LaboratoryApplication,
        ],
    ):
        if not callable(application_factory):
            raise TypeError(
                "application_factory must be callable"
            )

        self.application_factory = application_factory

    def commands(self):
        application = self._application()

        command_payloads = [
            command.as_dict()
            for command in application.commands()
        ]

        return ApplicationCommandResult(
            command="commands",
            success=True,
            value=len(command_payloads),
            data={
                "controller_family": (
                    application.controller_family
                ),
                "command_count": len(command_payloads),
                "commands": command_payloads,
            },
            message=(
                f"{len(command_payloads)} cataloged commands"
            ),
        )

    def execute(
        self,
        command_name,
        *,
        live=False,
    ):
        if (
            not isinstance(command_name, str)
            or not command_name.strip()
        ):
            raise ValueError(
                "command_name is required"
            )

        if not isinstance(live, bool):
            raise TypeError(
                "live must be a boolean"
            )

        application = self._application()

        result = application.execute(
            command_name.strip(),
            live=live,
        )

        return self._execution_result(result)

    def _application(self):
        application = self.application_factory()

        if not isinstance(
            application,
            LaboratoryApplication,
        ):
            raise TypeError(
                (
                    "application_factory must return "
                    "a LaboratoryApplication"
                )
            )

        return application

    @staticmethod
    def _execution_result(
        result: ExecutionResult,
    ):
        if not isinstance(
            result,
            ExecutionResult,
        ):
            raise TypeError(
                "result must be an ExecutionResult"
            )

        payload = result.as_dict()

        data = {
            "request_id": result.request_id,
            "opcode": result.opcode,
            "opcode_hex": (
                f"0x{result.opcode:02X}"
            ),
            "status": result.status.value,
            "decision": result.decision.reason.value,
            "duration_ms": result.duration_ms,
            "result": result.data,
            "metadata": dict(result.metadata),
        }

        if result.error:
            data["error"] = result.error

        return ApplicationCommandResult(
            command=f"execute-{result.command}",
            success=result.success,
            value=result.data,
            data=data,
            message=result.decision.message,
            capture_path=result.capture_path,
            error=result.error,
        )


def format_command_catalog(result):
    """
    Render a human-readable command catalog.
    """

    if not isinstance(
        result,
        ApplicationCommandResult,
    ):
        raise TypeError(
            (
                "result must be an "
                "ApplicationCommandResult"
            )
        )

    data = result.data or {}
    commands = data.get("commands", ())

    lines = [
        "Project Stargate Command Catalog",
        "================================",
        "",
        (
            "Controller : "
            f"{data.get('controller_family', 'unknown')}"
        ),
        f"Commands   : {len(commands)}",
        "",
    ]

    for command in commands:
        mode = (
            "read-only"
            if command["read_only"]
            else "write"
        )

        lines.append(
            f"{command['opcode_hex']}  "
            f"{command['name']:<16} "
            f"{command['safety']:<24} "
            f"{mode}"
        )

    return "\n".join(lines)


def format_execution_result(result):
    """
    Render a human-readable execution result.
    """

    if not isinstance(
        result,
        ApplicationCommandResult,
    ):
        raise TypeError(
            (
                "result must be an "
                "ApplicationCommandResult"
            )
        )

    data = result.data or {}
    metadata = data.get("metadata", {})

    lines = [
        "Project Stargate Execution",
        "===========================",
        "",
        f"Command  : {result.command.removeprefix('execute-')}",
        f"Opcode   : {data.get('opcode_hex', 'unknown')}",
        f"Status   : {data.get('status', 'unknown').upper()}",
        f"Decision : {data.get('decision', 'unknown')}",
        f"Message  : {result.message}",
        f"Duration : {data.get('duration_ms', 0.0):.3f} ms",
    ]

    if "value_hex" in metadata:
        lines.append(
            f"Value    : {metadata['value_hex']}"
        )
    elif result.value is not None:
        lines.append(
            f"Value    : {result.value}"
        )

    if result.capture_path:
        lines.append(
            f"Capture  : {result.capture_path}"
        )

    if result.error:
        lines.append(
            f"Error    : {result.error}"
        )

    return "\n".join(lines)
