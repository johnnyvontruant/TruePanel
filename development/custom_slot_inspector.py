#!/usr/bin/env python3
"""
Inspect A125 character codes 0x00 through 0x07 individually.

This uses only the documented display-write path and does not attempt to
program custom characters.
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
        "custom-slot-inspector",
        "/dev/ttyS1",
        1200,
        1.0,
        "development/logs",
    ) as (controller, capture):
        controller.backlight(True)
        controller.clear()

        for slot in range(8):
            controller.write_frame(
                f"SLOT 0x{slot:02X}",
                bytes([slot] * 16),
            )

            answer = input(
                f"Viewing slot 0x{slot:02X}. "
                "Describe it, Enter=skip, q=quit: "
            ).strip()

            if answer.lower() == "q":
                break

            observations.append(
                (slot, answer or "unrecorded")
            )

        controller.clear()

    print()
    print("Capture:", capture)
    print("Observations:")

    for slot, description in observations:
        print(
            f"  0x{slot:02X}: {description}"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
