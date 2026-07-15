"""
Execution interlock for Project Stargate surveys.

Hardware execution is limited to documented read-only A125 queries. Unknown
opcodes, documented writes, and blocked commands cannot pass this interlock.
"""

from __future__ import annotations

import time
from typing import Callable

from truepanel.diagnostics.protocol import (
    A125Reply,
    A125Response,
)
from truepanel.lab.classifier import (
    ResponseClassification,
    classify_error,
    classify_reply,
)
from truepanel.lab.survey_models import (
    ExecutionAuthorization,
    ExecutionContext,
    ExecutionObservation,
    ExecutionState,
)
from truepanel.lab.survey import (
    OpcodeRisk,
    SurveyPlan,
)


ARMING_PHRASE = "STARGATE SAFE READ ONLY"

SAFE_QUERY_RESPONSES = {
    0x00: A125Response.BOARD_ID,
    0x06: A125Response.BUTTON_STATUS,
    0x07: A125Response.PROTOCOL_VERSION,
}


def validate_execution_context(
    context: ExecutionContext,
) -> None:
    """Validate an execution request before any runner can begin."""

    if context.cooldown_seconds < 0:
        raise ValueError(
            "Execution cooldown cannot be negative"
        )

    if context.plan.count < 1:
        raise ValueError(
            "Execution plan must contain at least one opcode"
        )

    for entry in context.plan.entries:
        if entry.policy.risk != OpcodeRisk.SAFE_READ_ONLY:
            raise PermissionError(
                f"{entry.opcode_hex} cannot pass the hardware "
                f"interlock because it is {entry.policy.risk.value}"
            )

        if entry.opcode not in SAFE_QUERY_RESPONSES:
            raise PermissionError(
                f"{entry.opcode_hex} has no approved read-only runner"
            )

    if context.authorization.hardware_requested:
        if (
            context.authorization.arming_phrase
            != ARMING_PHRASE
        ):
            raise PermissionError(
                "Hardware execution requires the exact arming phrase: "
                f"{ARMING_PHRASE}"
            )

    context.state = ExecutionState.VALIDATED


def arm_execution(context: ExecutionContext) -> None:
    """Validate and arm one execution context."""

    validate_execution_context(context)

    if context.authorization.simulation:
        context.state = ExecutionState.ARMED
        return

    if (
        context.authorization.arming_phrase
        != ARMING_PHRASE
    ):
        raise PermissionError(
            "Execution authorization failed"
        )

    context.state = ExecutionState.ARMED


def build_execution_context(
    plan: SurveyPlan,
    simulation: bool = True,
    arming_phrase: str = "",
    cooldown_seconds: float = 0.10,
    stop_on_failure: bool = True,
) -> ExecutionContext:
    """Build and arm a survey execution context."""

    context = ExecutionContext(
        plan=plan,
        authorization=ExecutionAuthorization(
            simulation=bool(simulation),
            arming_phrase=str(arming_phrase),
        ),
        cooldown_seconds=float(cooldown_seconds),
        stop_on_failure=bool(stop_on_failure),
    )

    arm_execution(context)
    return context


def resolve_safe_query(
    controller,
    opcode: int,
) -> tuple[Callable[[], int], int]:
    """Resolve one approved read-only A125 query."""

    methods = {
        0x00: controller.query_board_id,
        0x06: controller.query_buttons,
        0x07: controller.query_protocol_version,
    }

    try:
        query = methods[opcode]
        response = SAFE_QUERY_RESPONSES[opcode]
    except KeyError as error:
        raise PermissionError(
            f"Opcode 0x{opcode:02X} has no approved query runner"
        ) from error

    return query, int(response)


def normalized_reply(
    response_code: int,
    value: int,
) -> A125Reply:
    """Construct a normalized classified response from a decoded value."""

    value = int(value)

    if not 0 <= value <= 0xFFFF:
        raise ValueError(
            "Read-only query value must fit in 16 bits"
        )

    return A125Reply(
        preamble=0x53,
        response=response_code,
        payload=value.to_bytes(2, "big"),
    )


def run_simulated_execution(
    context: ExecutionContext,
    callback: Callable[[ExecutionObservation], None] | None = None,
) -> ExecutionContext:
    """Execute a survey without opening or touching hardware."""

    if context.state != ExecutionState.ARMED:
        raise RuntimeError(
            "Execution context must be armed before running"
        )

    context.mark_started()

    for index, entry in enumerate(context.plan.entries):
        observation = ExecutionObservation(
            opcode=entry.opcode,
            success=True,
            simulated=True,
            latency_ms=0.0,
            detail="Simulation only; no bytes transmitted",
        )

        context.add(observation)

        if callback is not None:
            callback(observation)

        if (
            index + 1 < context.plan.count
            and context.cooldown_seconds > 0
        ):
            time.sleep(context.cooldown_seconds)

    context.mark_completed()
    return context


def run_hardware_execution(
    context: ExecutionContext,
    controller,
    callback: Callable[[ExecutionObservation], None] | None = None,
) -> ExecutionContext:
    """Run approved read-only queries against an A125 controller."""

    if context.state != ExecutionState.ARMED:
        raise RuntimeError(
            "Execution context must be armed before running"
        )

    if context.authorization.simulation:
        raise RuntimeError(
            "Simulation context cannot execute hardware queries"
        )

    context.mark_started()

    for index, entry in enumerate(context.plan.entries):
        started = time.perf_counter()

        try:
            query, expected_response = resolve_safe_query(
                controller,
                entry.opcode,
            )

            value = int(query())
            elapsed_ms = (
                time.perf_counter() - started
            ) * 1000.0

            response = classify_reply(
                normalized_reply(
                    expected_response,
                    value,
                )
            )

            success = (
                response.classification
                == ResponseClassification.KNOWN_RESPONSE
            )

            observation = ExecutionObservation(
                opcode=entry.opcode,
                success=success,
                simulated=False,
                latency_ms=elapsed_ms,
                value=value,
                response=response,
            )
        except Exception as error:
            elapsed_ms = (
                time.perf_counter() - started
            ) * 1000.0

            observation = ExecutionObservation(
                opcode=entry.opcode,
                success=False,
                simulated=False,
                latency_ms=elapsed_ms,
                response=classify_error(error),
                detail=f"{type(error).__name__}: {error}",
            )

        context.add(observation)

        if callback is not None:
            callback(observation)

        if not observation.success and context.stop_on_failure:
            context.abort(
                f"Stopped after failure at "
                f"0x{entry.opcode:02X}"
            )
            return context

        if (
            index + 1 < context.plan.count
            and context.cooldown_seconds > 0
        ):
            time.sleep(context.cooldown_seconds)

    context.mark_completed()
    return context


class SurveyService:
    """
    Application-facing survey orchestrator.

    The service owns survey preparation and dispatch while preserving the
    proven simulation and documented read-only hardware execution behavior.
    CLI callers do not interact with the legacy execution functions directly.
    """

    def prepare(
        self,
        *,
        plan,
        simulation=True,
        arming_phrase="",
        cooldown_seconds=0.10,
        stop_on_failure=True,
    ):
        return build_execution_context(
            plan=plan,
            simulation=simulation,
            arming_phrase=arming_phrase,
            cooldown_seconds=cooldown_seconds,
            stop_on_failure=stop_on_failure,
        )

    def run(
        self,
        context,
        *,
        controller=None,
        callback=None,
    ):
        if context.authorization.simulation:
            if controller is not None:
                raise ValueError(
                    "simulation surveys cannot receive a controller"
                )

            return run_simulated_execution(
                context,
                callback=callback,
            )

        if controller is None:
            raise ValueError(
                "hardware surveys require a controller"
            )

        return run_hardware_execution(
            context,
            controller,
            callback=callback,
        )

