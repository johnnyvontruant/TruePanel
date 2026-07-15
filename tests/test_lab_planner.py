"""
Tests for Project Stargate survey planning.

Run with:

    PYTHONPATH=. python3 tests/test_lab_planner.py
"""

from __future__ import annotations

from truepanel.lab.planner import (
    build_plan_from_expression,
    parse_opcode,
    parse_opcode_expression,
)
from truepanel.lab.survey import OpcodeRisk


def test_parse_opcode():
    assert parse_opcode("0x10") == 0x10
    assert parse_opcode("16") == 16
    assert parse_opcode(0x7D) == 0x7D


def test_parse_opcode_expression():
    assert parse_opcode_expression(
        "0x00,0x06-0x08,15"
    ) == [
        0x00,
        0x06,
        0x07,
        0x08,
        15,
    ]


def test_duplicate_opcodes_removed():
    assert parse_opcode_expression(
        "0x00,0x00,0x00-0x01"
    ) == [
        0x00,
        0x01,
    ]


def test_reversed_range_rejected():
    try:
        parse_opcode_expression("0x10-0x08")
    except ValueError:
        pass
    else:
        raise AssertionError(
            "Reversed range should fail"
        )


def test_safe_plan():
    plan = build_plan_from_expression(
        "0x00,0x06,0x07"
    )

    assert plan.count == 3
    assert all(
        entry.policy.risk == OpcodeRisk.SAFE_READ_ONLY
        for entry in plan.entries
    )


def test_unknown_defaults_to_stateful():
    try:
        build_plan_from_expression("0x10")
    except PermissionError as error:
        assert "stateful" in str(error).lower()
    else:
        raise AssertionError(
            "Unknown opcode should default to stateful"
        )


def test_stateful_authorization():
    plan = build_plan_from_expression(
        "0x10-0x12",
        allow_experimental_stateful=True,
    )

    assert plan.count == 3
    assert all(
        entry.policy.risk
        == OpcodeRisk.EXPERIMENTAL_STATEFUL
        for entry in plan.entries
    )


def test_documented_write_separate_authorization():
    try:
        build_plan_from_expression(
            "0x0C",
            allow_experimental_stateful=True,
        )
    except PermissionError:
        pass
    else:
        raise AssertionError(
            "Documented write needs separate authorization"
        )


def test_blocked_opcode_always_rejected():
    try:
        build_plan_from_expression(
            "0xFF",
            allow_experimental_read_only=True,
            allow_experimental_stateful=True,
            allow_documented_writes=True,
        )
    except PermissionError:
        pass
    else:
        raise AssertionError(
            "Blocked opcode should never be authorized"
        )


def main():
    tests = [
        test_parse_opcode,
        test_parse_opcode_expression,
        test_duplicate_opcodes_removed,
        test_reversed_range_rejected,
        test_safe_plan,
        test_unknown_defaults_to_stateful,
        test_stateful_authorization,
        test_documented_write_separate_authorization,
        test_blocked_opcode_always_rejected,
    ]

    for test in tests:
        test()
        print(f"PASS: {test.__name__}")

    print()
    print("Project Stargate Mission 3C.3: PASS")


if __name__ == "__main__":
    main()
