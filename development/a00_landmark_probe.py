#!/usr/bin/env python3
"""
Verify whether the A125 display uses the HD44780 A00 character ROM.

Displays selected landmark bytes from widely separated columns. Each glyph is
repeated across the second row to make visual comparison easier.
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
    0x85,
    0x8F,
    0x90,
    0x95,
    0x9F,
    0xA0,
    0xA5,
    0xAF,
    0xB0,
    0xB5,
    0xBF,
    0xC0,
    0xC5,
    0xCF,
    0xD0,
    0xD5,
    0xDF,
    0xE0,
    0xE5,
    0xEF,
    0xF0,
    0xF5,
    0xFE,
    0xFF,
)


def display_landmark(
    controller,
    value: int,
) -> None:
    controller.write_frame(
        f"A00 TEST 0x{value:02X}",
        bytes([value]) * LCD_WIDTH,
    )


def main() -> int:
    observations = []

    with open_controller(
        "a00-landmark-probe",
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

            answer = input(
                f"0x{value:02X}: "
                "match / different / uncertain / q: "
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
    print("Capture:", capture)
    print()
    print("A00 landmark results")
    print("====================")

    for item in observations:
        suffix = (
            f" - {item['notes']}"
            if item["notes"]
            else ""
        )

        print(
            f"{item['hex']}: "
            f"{item['result']}"
            f"{suffix}"
        )

    print()
    print(f"Matches:   {matches}")
    print(f"Different: {different}")
    print(f"Uncertain: {uncertain}")
    print(f"Checked:   {len(observations)}")

    if observations:
        confidence = (
            matches / len(observations)
        ) * 100

        print(
            f"A00 agreement: {confidence:.1f}%"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
