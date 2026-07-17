#!/usr/bin/env python3
"""
Compare suspected A125 ROM-code mappings side by side.

The left eight LCD cells show the transmitted byte.
The right eight cells show the suspected HD44780 A00 chart byte.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from truepanel.lab.capture import open_controller


PAIRS = (
    (0xAF, 0xC2),
)


def main() -> int:
    observations = []

    with open_controller(
        "rom-code-pair-probe",
        "/dev/ttyS1",
        1200,
        1.0,
        "development/logs",
    ) as (controller, capture):
        controller.backlight(True)
        controller.clear()

        for transmitted, chart_code in PAIRS:
            payload = bytes(
                [transmitted] * 8
                + [chart_code] * 8
            )

            controller.write_frame(
                f"{transmitted:02X} LEFT {chart_code:02X} RIGHT",
                payload,
            )

            result = input(
                f"Compare 0x{transmitted:02X} on the left "
                f"with 0x{chart_code:02X} on the right. "
                "same/different/uncertain/q: "
            ).strip().lower()

            if result == "q":
                break

            if result not in {
                "same",
                "different",
                "uncertain",
            }:
                result = "uncertain"

            notes = input(
                "Optional notes: "
            ).strip()

            observations.append(
                (
                    transmitted,
                    chart_code,
                    result,
                    notes,
                )
            )

        controller.clear()

    print()
    print("Capture:", capture)
    print("Results:")

    for transmitted, chart_code, result, notes in observations:
        suffix = f" - {notes}" if notes else ""

        print(
            f"  0x{transmitted:02X} vs "
            f"0x{chart_code:02X}: "
            f"{result}{suffix}"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
