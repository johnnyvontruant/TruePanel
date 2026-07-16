#!/usr/bin/env python3
"""
Compare A125 character codes 0x00-0x07 with 0x08-0x0F.

Many HD44780-compatible LCDs alias these ranges to the same eight CGRAM
slots. This tool uses only the documented display-write path.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from truepanel.lab.capture import open_controller


def main():
    observations = []

    with open_controller(
        "cgram-alias-inspector",
        "/dev/ttyS1",
        1200,
        1.0,
        "development/logs",
    ) as (controller, capture):
        controller.backlight(True)
        controller.clear()

        for slot in range(8):
            alias = slot + 8

            controller.write_frame(
                f"0x{slot:02X} VS 0x{alias:02X}",
                bytes(
                    [slot] * 8
                    + [alias] * 8
                ),
            )

            answer = input(
                f"Compare 0x{slot:02X} and 0x{alias:02X}. "
                "same/different/q: "
            ).strip().lower()

            if answer == "q":
                break

            observations.append(
                (
                    slot,
                    alias,
                    answer or "unrecorded",
                )
            )

        controller.clear()

    print()
    print("Capture:", capture)
    print("Alias observations:")

    for slot, alias, result in observations:
        print(
            f"  0x{slot:02X} vs 0x{alias:02X}: {result}"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
