"""
Project Stargate laboratory application layer.

LaboratoryApplication is the reusable application-facing API for Project
Stargate. CLI commands, plugins, automated discovery, dashboards, and future
remote interfaces should call this layer instead of assembling execution
components directly.

This first application slice exposes catalog-bound execution workflows only.
Existing fingerprint, capability, display, timing, and glyph CLI handlers can
be migrated into this layer incrementally.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .execution import ExecutionResult
from .execution_events import (
    ExecutionEvent,
    ExecutionEventBus,
    ExecutionEventListener,
    ExecutionEventRecorder,
)
from .execution_service import (
    ExecutionService,
    PreparedExecution,
    build_a125_execution_service,
)
from .interlock import ExecutionMode


@dataclass(frozen=True)
class CatalogCommandSummary:
    name: str
    opcode: int
    opcode_hex: str
    category: str
    safety: str
    danger_level: str
    documented: bool
    read_only: bool
    requires_live_hardware: bool
    description: str

    def as_dict(self):
        return {
            "name": self.name,
            "opcode": self.opcode,
            "opcode_hex": self.opcode_hex,
            "category": self.category,
            "safety": self.safety,
            "danger_level": self.danger_level,
            "documented": self.documented,
            "read_only": self.read_only,
            "requires_live_hardware": (
                self.requires_live_hardware
            ),
            "description": self.description,
        }


@dataclass(frozen=True)
class LaboratoryApplicationConfiguration:
    controller_family: str = "A125"
    cooldown_seconds: float = 1.0
    require_fingerprint: bool = True
    event_history_size: int = 1000

    def __post_init__(self):
        if (
            not self.controller_family
            or not self.controller_family.strip()
        ):
            raise ValueError(
                "controller_family is required"
            )

        if self.cooldown_seconds < 0:
            raise ValueError(
                "cooldown_seconds cannot be negative"
            )

        if self.event_history_size <= 0:
            raise ValueError(
                "event_history_size must be greater than zero"
            )


class LaboratoryApplication:
    """
    Public application API for Project Stargate execution workflows.

    The application owns the execution service and event recorder. This keeps
    safety configuration, cooldown state, and execution history consistent
    across repeated calls.
    """

    def __init__(
        self,
        execution_service: ExecutionService,
        *,
        event_recorder: ExecutionEventRecorder | None = None,
    ):
        if not isinstance(
            execution_service,
            ExecutionService,
        ):
            raise TypeError(
                "execution_service must be an ExecutionService"
            )

        self.execution_service = execution_service

        self.event_recorder = (
            event_recorder
            if event_recorder is not None
            else ExecutionEventRecorder()
        )

        self._ensure_recorder_subscription()

    @property
    def controller_family(self):
        return self.execution_service.controller_family

    @property
    def catalog(self):
        return self.execution_service.catalog

    @property
    def event_bus(self):
        return self.execution_service.event_bus

    def prepare(
        self,
        command_name,
        *,
        live=False,
        payload=b"",
    ) -> PreparedExecution:
        """
        Prepare one catalog-bound command without executing it.
        """

        return self.execution_service.prepare(
            command_name,
            mode=self._execution_mode(live),
            payload=payload,
        )

    def authorize(
        self,
        prepared,
        *,
        operator="unknown",
        lifetime_seconds=60,
        now=None,
    ):
        """
        Issue request-bound authorization for a prepared execution.
        """

        return self.execution_service.authorize(
            prepared,
            operator=operator,
            lifetime_seconds=lifetime_seconds,
            now=now,
        )

    def execute(
        self,
        command_name,
        *,
        live=False,
        payload=b"",
        authorization=None,
        controller_family=None,
    ) -> ExecutionResult:
        """
        Execute one cataloged command.

        Simulation is the default. Setting live=True still passes through the
        catalog, fingerprint, authorization, cooldown, adapter, and event
        pipeline.
        """

        return self.execution_service.execute(
            command_name,
            mode=self._execution_mode(live),
            payload=payload,
            authorization=authorization,
            controller_family=controller_family,
        )

    def execute_prepared(
        self,
        prepared,
        *,
        authorization=None,
        controller_family=None,
    ) -> ExecutionResult:
        return self.execution_service.execute_prepared(
            prepared,
            authorization=authorization,
            controller_family=controller_family,
        )

    def simulate(
        self,
        command_name,
        *,
        payload=b"",
    ) -> ExecutionResult:
        return self.execute(
            command_name,
            live=False,
            payload=payload,
        )

    def execute_live(
        self,
        command_name,
        *,
        payload=b"",
        authorization=None,
        controller_family=None,
    ) -> ExecutionResult:
        return self.execute(
            command_name,
            live=True,
            payload=payload,
            authorization=authorization,
            controller_family=controller_family,
        )

    def commands(self):
        """
        Return immutable summaries of every cataloged command.
        """

        return tuple(
            CatalogCommandSummary(
                name=command.name,
                opcode=command.opcode,
                opcode_hex=command.opcode_hex,
                category=command.category.value,
                safety=command.safety.value,
                danger_level=command.danger_level.value,
                documented=command.documented,
                read_only=command.read_only,
                requires_live_hardware=(
                    command.requires_live_hardware
                ),
                description=command.description,
            )
            for command in self.catalog.commands()
        )

    def command(self, command_name):
        command = self.catalog.require(
            command_name
        )

        return CatalogCommandSummary(
            name=command.name,
            opcode=command.opcode,
            opcode_hex=command.opcode_hex,
            category=command.category.value,
            safety=command.safety.value,
            danger_level=command.danger_level.value,
            documented=command.documented,
            read_only=command.read_only,
            requires_live_hardware=(
                command.requires_live_hardware
            ),
            description=command.description,
        )

    def unknown_opcodes(
        self,
        *,
        start=0x00,
        end=0xFF,
    ):
        return self.catalog.unknown_opcodes(
            start=start,
            end=end,
        )

    def events(self):
        return self.event_recorder.events

    def latest_event(self):
        return self.event_recorder.latest()

    def failed_events(self):
        return self.event_recorder.failures()

    def events_for_command(
        self,
        command_name,
    ):
        return self.event_recorder.by_command(
            command_name
        )

    def clear_events(self):
        self.event_recorder.clear()

    def cooldown_remaining(
        self,
        command_name,
    ):
        return self.execution_service.cooldown_remaining(
            command_name
        )

    def clear_cooldown(
        self,
        command_name=None,
    ):
        self.execution_service.clear_cooldown(
            command_name
        )

    def subscribe(
        self,
        listener: (
            ExecutionEventListener
            | callable
        ),
    ):
        return self.event_bus.subscribe(
            listener
        )

    def unsubscribe(
        self,
        listener,
    ):
        return self.event_bus.unsubscribe(
            listener
        )

    def summary(self):
        return {
            "controller_family": self.controller_family,
            "command_count": len(self.catalog),
            "known_opcodes": list(
                self.catalog.opcodes()
            ),
            "unknown_opcode_count": len(
                self.catalog.unknown_opcodes()
            ),
            "event_count": len(
                self.event_recorder
            ),
            "cooldown_seconds": (
                self.execution_service
                .cooldown
                .cooldown_seconds
            ),
            "fingerprint_required": (
                self.execution_service
                .interlock
                .require_fingerprint
            ),
        }

    def _ensure_recorder_subscription(self):
        for listener in self.event_bus.listeners:
            if listener is self.event_recorder:
                return

        self.event_bus.subscribe(
            self.event_recorder
        )

    @staticmethod
    def _execution_mode(live):
        if not isinstance(live, bool):
            raise TypeError(
                "live must be a boolean"
            )

        if live:
            return ExecutionMode.LIVE

        return ExecutionMode.SIMULATION


def build_a125_laboratory_application(
    controller,
    *,
    configuration: (
        LaboratoryApplicationConfiguration
        | None
    ) = None,
    session_service=None,
    event_listeners: Iterable[
        ExecutionEventListener | callable
    ] = (),
    cooldown_clock=None,
    execution_clock=None,
):
    """
    Build the canonical A125 laboratory application.
    """

    configuration = (
        configuration
        or LaboratoryApplicationConfiguration()
    )

    event_recorder = ExecutionEventRecorder(
        max_events=configuration.event_history_size
    )

    event_bus = ExecutionEventBus(
        (
            event_recorder,
            *tuple(event_listeners),
        )
    )

    execution_service = build_a125_execution_service(
        controller,
        cooldown_seconds=(
            configuration.cooldown_seconds
        ),
        require_fingerprint=(
            configuration.require_fingerprint
        ),
        session_service=session_service,
        cooldown_clock=cooldown_clock,
        execution_clock=execution_clock,
        event_bus=event_bus,
    )

    return LaboratoryApplication(
        execution_service,
        event_recorder=event_recorder,
    )
