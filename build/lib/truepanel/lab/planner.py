"""
Dry-run survey planning for Project Stargate.

The planner parses opcode expressions and builds validated SurveyPlan objects.
It never opens the serial port and never transmits controller commands.
"""

from __future__ import annotations

from truepanel.lab.survey import (
    SurveyPlan,
    build_survey_plan,
)


def parse_opcode(value: str | int) -> int:
    """Parse a decimal or hexadecimal opcode."""

    if isinstance(value, int):
        opcode = value
    else:
        text = str(value).strip()

        if not text:
            raise ValueError("Opcode cannot be empty")

        opcode = int(text, 0)

    if not 0 <= opcode <= 0xFF:
        raise ValueError(
            f"Opcode must fit in one byte: {opcode}"
        )

    return opcode


def parse_opcode_expression(expression: str) -> list[int]:
    """
    Parse a comma-separated opcode expression.

    Supported examples:

        0x00
        0x00,0x06,0x07
        0x08-0x0B
        0x00,0x06-0x08,15
    """

    if not expression or not expression.strip():
        raise ValueError("Opcode expression cannot be empty")

    opcodes: list[int] = []

    for component in expression.split(","):
        component = component.strip()

        if not component:
            raise ValueError(
                "Opcode expression contains an empty component"
            )

        if "-" not in component:
            opcodes.append(parse_opcode(component))
            continue

        start_text, end_text = component.split("-", 1)
        start = parse_opcode(start_text)
        end = parse_opcode(end_text)

        if end < start:
            raise ValueError(
                f"Opcode range is reversed: {component}"
            )

        opcodes.extend(range(start, end + 1))

    return list(dict.fromkeys(opcodes))


def build_plan_from_expression(
    expression: str,
    allow_experimental_read_only: bool = False,
    allow_experimental_stateful: bool = False,
    allow_documented_writes: bool = False,
) -> SurveyPlan:
    """Parse and validate a survey expression."""

    return build_survey_plan(
        parse_opcode_expression(expression),
        allow_experimental_read_only=(
            allow_experimental_read_only
        ),
        allow_experimental_stateful=(
            allow_experimental_stateful
        ),
        allow_documented_writes=allow_documented_writes,
    )
