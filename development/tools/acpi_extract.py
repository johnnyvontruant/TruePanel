#!/usr/bin/env python3
"""
Extract selected AML/ASL objects and their references from a disassembled DSDT.

Read-only analysis tool. It does not evaluate ACPI methods or access hardware.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


DECLARATION_RE = re.compile(
    r"""
    ^(?P<indent>\s*)
    (?P<kind>
        Method|
        Device|
        Scope|
        PowerResource|
        Processor|
        ThermalZone|
        OperationRegion|
        Field|
        IndexField|
        BankField|
        Name
    )
    \s*\(
    """,
    re.VERBOSE,
)


def mask_line(line: str, in_block_comment: bool) -> tuple[str, bool]:
    """
    Replace comments and string contents with spaces so braces inside them
    do not interfere with block matching.
    """

    output: list[str] = []
    index = 0
    in_string = False

    while index < len(line):
        if in_block_comment:
            end = line.find("*/", index)
            if end < 0:
                output.append(" " * (len(line) - index))
                return "".join(output), True

            output.append(" " * (end + 2 - index))
            index = end + 2
            in_block_comment = False
            continue

        if not in_string and line.startswith("/*", index):
            output.append("  ")
            index += 2
            in_block_comment = True
            continue

        if not in_string and line.startswith("//", index):
            output.append(" " * (len(line) - index))
            break

        char = line[index]

        if char == '"':
            in_string = not in_string
            output.append(" ")
        elif in_string:
            output.append(" ")
        else:
            output.append(char)

        index += 1

    return "".join(output), in_block_comment


def brace_map(lines: list[str]) -> tuple[list[int], list[int]]:
    opens: list[int] = []
    closes: list[int] = []
    stack: list[int] = []
    in_block_comment = False

    for line_number, line in enumerate(lines):
        masked, in_block_comment = mask_line(line, in_block_comment)

        for char in masked:
            if char == "{":
                stack.append(line_number)
                opens.append(line_number)
            elif char == "}":
                closes.append(line_number)
                if stack:
                    stack.pop()

    return opens, closes


def find_block_end(lines: list[str], start: int) -> int:
    depth = 0
    found_open = False
    in_block_comment = False

    for line_number in range(start, len(lines)):
        masked, in_block_comment = mask_line(
            lines[line_number],
            in_block_comment,
        )

        for char in masked:
            if char == "{":
                depth += 1
                found_open = True
            elif char == "}" and found_open:
                depth -= 1
                if depth == 0:
                    return line_number

    # Name() and OperationRegion() declarations may not have braces.
    return start


def declaration_name(line: str) -> tuple[str, str] | None:
    match = DECLARATION_RE.search(line)
    if not match:
        return None

    kind = match.group("kind")
    remainder = line[match.end():]

    name_match = re.match(r"\s*([^,\s\)]+)", remainder)
    if not name_match:
        return None

    return kind, name_match.group(1)


def declaration_ranges(
    lines: list[str],
) -> list[tuple[int, int, str, str]]:
    ranges: list[tuple[int, int, str, str]] = []

    for index, line in enumerate(lines):
        parsed = declaration_name(line)
        if parsed is None:
            continue

        kind, name = parsed
        end = find_block_end(lines, index)
        ranges.append((index, end, kind, name))

    return ranges


def enclosing_object(
    line_number: int,
    ranges: list[tuple[int, int, str, str]],
) -> tuple[int, int, str, str] | None:
    candidates = [
        item
        for item in ranges
        if item[0] <= line_number <= item[1]
    ]

    if not candidates:
        return None

    # Smallest enclosing block is the most specific one.
    return min(candidates, key=lambda item: item[1] - item[0])


def print_range(
    lines: list[str],
    start: int,
    end: int,
    *,
    heading: str,
) -> None:
    print()
    print("=" * 78)
    print(heading)
    print("=" * 78)

    for index in range(start, end + 1):
        print(f"{index + 1:6}: {lines[index]}", end="")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("dsl", type=Path)
    parser.add_argument(
        "symbols",
        nargs="+",
        help="ACPI names to extract and trace",
    )
    parser.add_argument(
        "--context",
        type=int,
        default=8,
        help="Reference context lines",
    )
    args = parser.parse_args()

    if not args.dsl.is_file():
        print(f"DSDT file not found: {args.dsl}", file=sys.stderr)
        return 1

    lines = args.dsl.read_text(
        encoding="utf-8",
        errors="replace",
    ).splitlines(keepends=True)

    ranges = declaration_ranges(lines)
    printed_ranges: set[tuple[int, int]] = set()

    print(f"DSDT: {args.dsl}")
    print(f"Lines: {len(lines)}")
    print("Symbols:", ", ".join(args.symbols))

    for symbol in args.symbols:
        pattern = re.compile(
            rf"(?<![A-Za-z0-9_]){re.escape(symbol)}"
            rf"(?![A-Za-z0-9_])",
            re.IGNORECASE,
        )

        references = [
            index
            for index, line in enumerate(lines)
            if pattern.search(line)
        ]

        print()
        print("#" * 78)
        print(f"SYMBOL {symbol}: {len(references)} reference(s)")
        print("#" * 78)

        if not references:
            continue

        # Print declarations or enclosing Field/Method blocks.
        for reference in references:
            enclosing = enclosing_object(reference, ranges)

            if enclosing is None:
                continue

            start, end, kind, name = enclosing
            key = (start, end)

            if key in printed_ranges:
                continue

            printed_ranges.add(key)
            print_range(
                lines,
                start,
                end,
                heading=(
                    f"ENCLOSING OBJECT FOR {symbol}: "
                    f"{kind} {name}, lines {start + 1}-{end + 1}"
                ),
            )

        # Print every call/reference with compact context.
        for reference in references:
            start = max(0, reference - args.context)
            end = min(len(lines) - 1, reference + args.context)

            print_range(
                lines,
                start,
                end,
                heading=(
                    f"REFERENCE TO {symbol} AT LINE {reference + 1}"
                ),
            )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
