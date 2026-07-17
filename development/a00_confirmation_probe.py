#!/usr/bin/env python3
"""
Confirm the A125 extended character ROM against HD44780 A00 landmarks.

Each selected byte is shown individually across the second LCD row. The
operator compares it with the exact same binary coordinate in the A00 chart.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from truepanel.lab.capture import open_controller


LCD_WIDTH = 16

LANDMARKS = (
    0x80,
    0x91,
    0xA5,
    0xAF,
    0xC2,
    0xD7,
    0xE9,
    0xFF,
)


def binary_byte(value: int) -> str:
    return f"{value:08b}"


def display_landmark(
    controller,
    value: int,
) -> None:
    controller.write_frame(
        f"0x{value:02X} {binary_byte(value)}",
        bytes([value]) * LCD_WIDTH,
    )


def main() -> int:
    observations = []

    with open_controller(
        "a00-confirmation-probe",
        "/dev/ttyS1",
        1200,
        1.0,
        "development/logs",
    ) as (controller, capture):
        controller.backlight(True)
        controller.clear()

        for value in LANDMARKS:
            display_landmark(
                controller,
                value,
            )

            upper = value >> 4
            lower = value & 0x0F

            print()
            print(
                f"Byte 0x{value:02X} = "
                f"{upper:04b} {lower:04b}"
            )
            print(
                f"Chart row: {upper:04b}"
            )
            print(
                f"Chart column: {lower:04b}"
            )

            answer = input(
                "Does the LCD match that A00 chart cell? "
                "match/different/uncertain/q: "
            ).strip().lower()

            if answer == "q":
                break

            if answer not in {
                "match",
                "different",
                "uncertain",
            }:
                answer = "uncertain"

            notes = input(
                "Optional notes: "
            ).strip()

            observations.append(
                {
                    "value": value,
                    "hex": f"0x{value:02X}",
                    "binary": binary_byte(value),
                    "result": answer,
                    "notes": notes,
                }
            )

        controller.clear()

    matches = sum(
        item["result"] == "match"
        for item in observations
    )
    different = sum(
        item["result"] == "different"
        for item in observations
    )
    uncertain = sum(
        item["result"] == "uncertain"
        for item in observations
    )

    print()
    print("A00 Confirmation Results")
    print("========================")

    for item in observations:
        suffix = (
            f" - {item['notes']}"
            if item["notes"]
            else ""
        )

        print(
            f"{item['hex']} "
            f"{item['binary']}: "
            f"{item['result']}"
            f"{suffix}"
        )

    print()
    print(f"Matches:   {matches}")
    print(f"Different: {different}")
    print(f"Uncertain: {uncertain}")
    print(f"Checked:   {len(observations)}")

    if observations:
        agreement = (
            matches / len(observations)
        ) * 100

        print(
            f"A00 agreement: {agreement:.1f}%"
        )

    print()
    print("Capture:", capture)

    if (
        len(observations) == len(LANDMARKS)
        and matches == len(LANDMARKS)
    ):
        print()
        print(
            "RESULT: HD44780 A00 CGROM CONFIRMED"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
