#!/usr/bin/env python3
"""
Locate ECMD calls and report their enclosing ACPI methods.

Read-only DSDT analysis.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path


METHOD_RE = re.compile(
    r'^\s*Method\s*\(\s*([A-Z0-9_]+)\s*,',
    re.IGNORECASE,
)

CALL_RE = re.compile(
    r'\bECMD\s*\(\s*(0x[0-9A-F]+|\d+)\s*\)',
    re.IGNORECASE,
)


def masked_line(line: str, block_comment: bool) -> tuple[str, bool]:
    output = []
    index = 0
    in_string = False

    while index < len(line):
        if block_comment:
            end = line.find("*/", index)
            if end == -1:
                return "".join(output), True

            index = end + 2
            block_comment = False
            continue

        if not in_string and line.startswith("/*", index):
            block_comment = True
            index += 2
            continue

        if not in_string and line.startswith("//", index):
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

    return "".join(output), block_comment


def method_ranges(lines: list[str]):
    ranges = []
    block_comment = False

    for start, line in enumerate(lines):
        match = METHOD_RE.search(line)
        if not match:
            continue

        name = match.group(1)
        depth = 0
        opened = False
        local_comment = block_comment

        for end in range(start, len(lines)):
            masked, local_comment = masked_line(
                lines[end],
                local_comment,
            )

            depth += masked.count("{")
            if "{" in masked:
                opened = True

            depth -= masked.count("}")

            if opened and depth == 0:
                ranges.append((start, end, name))
                break

    return ranges


def enclosing_method(line_number, ranges):
    candidates = [
        item
        for item in ranges
        if item[0] <= line_number <= item[1]
    ]

    if not candidates:
        return None

    return min(candidates, key=lambda item: item[1] - item[0])


def main():
    if len(sys.argv) != 2:
        raise SystemExit(
            "usage: acpi_ec_callgraph.py /path/to/DSDT.dsl"
        )

    path = Path(sys.argv[1])
    lines = path.read_text(
        encoding="utf-8",
        errors="replace",
    ).splitlines()

    ranges = method_ranges(lines)

    targets = set(range(0x28, 0x33))
    found = 0

    for line_number, line in enumerate(lines):
        for match in CALL_RE.finditer(line):
            command = int(match.group(1), 0)

            if command not in targets:
                continue

            owner = enclosing_method(line_number, ranges)
            method_name = owner[2] if owner else "<global>"

            print(
                f"0x{command:02X}  "
                f"line={line_number + 1:<6} "
                f"method={method_name:<8} "
                f"{line.strip()}"
            )
            found += 1

    if not found:
        print("No ECMD calls found for commands 0x28-0x32.")


if __name__ == "__main__":
    main()
