"""
Tests for the Project Stargate Execution Interlock.

Run with:

    PYTHONPATH=. python3 tests/test_lab_interlock.py
"""

from __future__ import annotations

from truepanel.lab.execution import ExecutionState
from truepanel.lab.interlock import (
    ARMING_PHRASE,
    build_execution_context,
    run_hardware_execution,
    run_simulated_execution,
)
from truepanel.lab.planner import build_plan_from_expression


class FakeController:
    def query_board_id(self):
        return 0x007D

    def query_protocol_version(self):
        return 0x0003

    def query_buttons(self):
        return 0x0000


class FailingController(FakeController):
    def query_protocol_version(self):
        raise TimeoutError("simulated timeout")


def safe_plan():
    return build_plan_from_expression(
        "0x00,0x06,0x07"
    )


def test_simulation_arms_without_phrase():
    context = build_execution_context(
        safe_plan(),
        simulation=True,
        cooldown_seconds=0,
    )

    assert context.state == ExecutionState.ARMED


def test_simulation_completes():
    context = build_execution_context(
        safe_plan(),
        simulation=True,
        cooldown_seconds=0,
    )

    run_simulated_execution(context)

    assert context.state == ExecutionState.COMPLETED
    assert context.healthy
    assert context.successes == 3
    assert all(
        observation.simulated
        for observation in context.observations
    )


def test_hardware_requires_exact_phrase():
    try:
        build_execution_context(
            safe_plan(),
            simulation=False,
            arming_phrase="close enough",
            cooldown_seconds=0,
        )
    except PermissionError:
        pass
    else:
        raise AssertionError(
            "Incorrect arming phrase should fail"
        )


def test_hardware_arms_with_exact_phrase():
    context = build_execution_context(
        safe_plan(),
        simulation=False,
        arming_phrase=ARMING_PHRASE,
        cooldown_seconds=0,
    )

    assert context.state == ExecutionState.ARMED


def test_stateful_opcode_rejected():
    plan = build_plan_from_expression(
        "0x10",
        allow_experimental_stateful=True,
    )

    try:
        build_execution_context(
            plan,
            simulation=True,
            cooldown_seconds=0,
        )
    except PermissionError:
        pass
    else:
        raise AssertionError(
            "Experimental stateful opcode passed interlock"
        )


def test_documented_write_rejected():
    plan = build_plan_from_expression(
        "0x0C",
        allow_documented_writes=True,
    )

    try:
        build_execution_context(
            plan,
            simulation=True,
            cooldown_seconds=0,
        )
    except PermissionError:
        pass
    else:
        raise AssertionError(
            "Documented write passed read-only interlock"
        )


def test_hardware_execution():
    context = build_execution_context(
        safe_plan(),
        simulation=False,
        arming_phrase=ARMING_PHRASE,
        cooldown_seconds=0,
    )

    run_hardware_execution(
        context,
        FakeController(),
    )

    assert context.state == ExecutionState.COMPLETED
    assert context.healthy
    assert context.successes == 3
    assert [
        observation.value
        for observation in context.observations
    ] == [
        0x007D,
        0x0000,
        0x0003,
    ]


def test_failure_aborts_execution():
    plan = build_plan_from_expression(
        "0x00,0x07,0x06"
    )

    context = build_execution_context(
        plan,
        simulation=False,
        arming_phrase=ARMING_PHRASE,
        cooldown_seconds=0,
    )

    run_hardware_execution(
        context,
        FailingController(),
    )

    assert context.state == ExecutionState.ABORTED
    assert context.failures == 1
    assert len(context.observations) == 2
    assert "0x07" in context.abort_reason


def main():
    tests = [
        test_simulation_arms_without_phrase,
        test_simulation_completes,
        test_hardware_requires_exact_phrase,
        test_hardware_arms_with_exact_phrase,
        test_stateful_opcode_rejected,
        test_documented_write_rejected,
        test_hardware_execution,
        test_failure_aborts_execution,
    ]

    for test in tests:
        test()
        print(f"PASS: {test.__name__}")

    print()
    print("Project Stargate Mission 3C.4: PASS")


if __name__ == "__main__":
    main()
