#!/usr/bin/env python3
"""
Map the A125 DISPLAY_WRITE selector byte.

Uses only documented opcode 0x0C. Each selector receives a distinctive
one-character payload so its visible behavior can be recorded.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from truepanel.lab.capture import open_controller


SELECTORS = (
    0x00,
    0x01,
    0x02,
    0x03,
    0x40,
    0x80,
)


def packet(selector: int, marker: str) -> bytes:
    return bytes(
        (
            0x4D,
            0x0C,
            selector,
            0x01,
            ord(marker),
        )
    )


def main():
    observations = []

    with open_controller(
        "display-selector-probe",
        "/dev/ttyS1",
        1200,
        1.0,
        "development/logs",
    ) as (controller, capture):
        controller.backlight(True)

        for index, selector in enumerate(SELECTORS):
            marker = chr(ord("A") + index)

            controller.clear()
            controller.write_frame(
                f"SELECT 0x{selector:02X}",
                "Watch for " + marker,
            )

            input(
                f"Baseline ready for selector 0x{selector:02X}. "
                "Press Enter to transmit..."
            )

            controller.send(
                packet(selector, marker)
            )

            result = input(
                f"Where did marker {marker} appear? "
                "Describe, or type ignored/q: "
            ).strip()

            if result.lower() == "q":
                break

            observations.append(
                (selector, marker, result or "unrecorded")
            )

        controller.clear()

    print()
    print("Capture:", capture)
    print("Observations:")

    for selector, marker, result in observations:
        print(
            f"  0x{selector:02X} marker {marker}: {result}"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
