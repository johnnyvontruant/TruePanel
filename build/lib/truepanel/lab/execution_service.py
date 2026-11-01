"""
Public execution service for Project Stargate.

ExecutionService is the canonical entry point for laboratory command
execution. Callers provide a cataloged command name and execution mode; the
service assembles and coordinates all safety-critical components.

The service intentionally exposes no arbitrary opcode execution method.
"""

from __future__ import annotations

from dataclasses import dataclass

from .a125_adapter import A125ExecutionAdapter
from .authorization import ExecutionAuthorization
from .catalog import (
    A125_COMMAND_CATALOG,
    CommandCatalog,
)
from .cooldown import CooldownTracker
from .execution import (
    ExecutionEngine,
    ExecutionResult,
)
from .execution_events import (
    ExecutionEvent,
    ExecutionEventBus,
)
from .interlock import (
    ExecutionInterlock,
    ExecutionMode,
    ExecutionRequest,
)
from .request_factory import CatalogRequestFactory


@dataclass(frozen=True)
class ExecutionServiceConfiguration:
    controller_family: str = "A125"
    cooldown_seconds: float = 1.0
    require_fingerprint: bool = True

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


@dataclass(frozen=True)
class PreparedExecution:
    """
    Catalog-built request awaiting execution.
    """

    request: ExecutionRequest

    @property
    def request_id(self):
        return self.request.request_id

    @property
    def command(self):
        return self.request.name

    @property
    def mode(self):
        return self.request.mode

    def as_dict(self):
        return {
            "request_id": self.request.request_id,
            "command": self.request.name,
            "opcode": self.request.opcode,
            "opcode_hex": (
                f"0x{self.request.opcode:02X}"
            ),
            "mode": self.request.mode.value,
            "danger_level": (
                self.request.danger_level.value
            ),
            "known_opcode": self.request.known_opcode,
            "expected_controller_family": (
                self.request.expected_controller_family
            ),
            "payload_hex": self.request.payload.hex(),
        }


class ExecutionService:
    """
    High-level safe execution facade.

    The service owns one shared cooldown tracker and execution engine, ensuring
    repeated calls cannot bypass rate limiting by accidentally constructing
    fresh policy objects.
    """

    def __init__(
        self,
        controller,
        *,
        catalog: CommandCatalog | None = None,
        configuration: ExecutionServiceConfiguration | None = None,
        session_service=None,
        cooldown_clock=None,
        execution_clock=None,
        event_bus=None,
    ):
        if controller is None:
            raise ValueError("controller is required")

        self.controller = controller
        self.catalog = catalog or A125_COMMAND_CATALOG
        self.configuration = (
            configuration
            or ExecutionServiceConfiguration()
        )
        self.session_service = session_service
        self.event_bus = (
            event_bus
            if event_bus is not None
            else ExecutionEventBus()
        )

        self.request_factory = CatalogRequestFactory(
            self.catalog,
            controller_family=(
                self.configuration.controller_family
            ),
        )

        self.cooldown = CooldownTracker(
            cooldown_seconds=(
                self.configuration.cooldown_seconds
            ),
            clock=cooldown_clock,
        )

        self.interlock = ExecutionInterlock(
            cooldown=self.cooldown,
            require_fingerprint=(
                self.configuration.require_fingerprint
            ),
        )

        self.adapter = A125ExecutionAdapter(
            controller,
            catalog=self.catalog,
        )

        self.engine = ExecutionEngine(
            self.interlock,
            self.adapter,
            session_service=session_service,
            clock=execution_clock,
        )

    @property
    def controller_family(self):
        return self.configuration.controller_family

    def prepare(
        self,
        command_name,
        *,
        mode=ExecutionMode.SIMULATION,
        payload=b"",
    ):
        """
        Build a canonical request without executing it.
        """

        request = self.request_factory.build(
            command_name,
            mode=mode,
            payload=payload,
        )

        return PreparedExecution(request=request)

    def authorize(
        self,
        prepared,
        *,
        operator="unknown",
        lifetime_seconds=60,
        now=None,
    ):
        """
        Issue authorization bound to one prepared request.

        Authorization alone does not bypass catalog, fingerprint, mode,
        cooldown, or danger-level policy.
        """

        request = self._extract_request(prepared)

        return ExecutionAuthorization.issue(
            request.request_id,
            operator=operator,
            lifetime_seconds=lifetime_seconds,
            now=now,
        )

    def execute_prepared(
        self,
        prepared,
        *,
        authorization=None,
        controller_family=None,
    ):
        """
        Execute a previously prepared request.
        """

        request = self._extract_request(prepared)

        effective_controller_family = (
            controller_family
            or self.controller_family
        )

        result = self.engine.execute(
            request,
            authorization=authorization,
            controller_family=(
                effective_controller_family
            ),
        )

        event = ExecutionEvent.from_result(
            result,
            controller_family=(
                effective_controller_family
            ),
        )

        self.event_bus.publish(event)

        return result

    def execute(
        self,
        command_name,
        *,
        mode=ExecutionMode.SIMULATION,
        payload=b"",
        authorization=None,
        controller_family=None,
    ):
        """
        Prepare and execute one cataloged command.

        Dangerous commands should normally use prepare(), authorize(), and
        execute_prepared() so authorization is bound to the exact request.
        """

        prepared = self.prepare(
            command_name,
            mode=mode,
            payload=payload,
        )

        return self.execute_prepared(
            prepared,
            authorization=authorization,
            controller_family=controller_family,
        )

    def simulate(
        self,
        command_name,
        *,
        payload=b"",
    ):
        return self.execute(
            command_name,
            mode=ExecutionMode.SIMULATION,
            payload=payload,
        )

    def execute_live(
        self,
        command_name,
        *,
        payload=b"",
        authorization=None,
        controller_family=None,
    ):
        return self.execute(
            command_name,
            mode=ExecutionMode.LIVE,
            payload=payload,
            authorization=authorization,
            controller_family=controller_family,
        )

    def cooldown_remaining(
        self,
        command_name,
    ):
        command = self.catalog.require(
            command_name
        )

        key = (
            self.controller_family,
            command.opcode,
        )

        return self.cooldown.remaining(key)

    def clear_cooldown(
        self,
        command_name=None,
    ):
        """
        Clear cooldown state.

        Intended for tests and deliberate administrative workflows. Normal
        command execution should allow cooldowns to expire naturally.
        """

        if command_name is None:
            self.cooldown.clear()
            return

        command = self.catalog.require(
            command_name
        )

        key = (
            self.controller_family,
            command.opcode,
        )

        self.cooldown.clear(key)

    @staticmethod
    def _extract_request(prepared):
        if isinstance(prepared, PreparedExecution):
            return prepared.request

        if isinstance(prepared, ExecutionRequest):
            return prepared

        raise TypeError(
            (
                "prepared must be a PreparedExecution "
                "or ExecutionRequest"
            )
        )


def build_a125_execution_service(
    controller,
    *,
    cooldown_seconds=1.0,
    require_fingerprint=True,
    session_service=None,
    cooldown_clock=None,
    execution_clock=None,
    event_bus=None,
):
    """
    Build the canonical A125 execution service.
    """

    configuration = ExecutionServiceConfiguration(
        controller_family="A125",
        cooldown_seconds=cooldown_seconds,
        require_fingerprint=require_fingerprint,
    )

    return ExecutionService(
        controller,
        catalog=A125_COMMAND_CATALOG,
        configuration=configuration,
        session_service=session_service,
        cooldown_clock=cooldown_clock,
        execution_clock=execution_clock,
        event_bus=event_bus,
    )
