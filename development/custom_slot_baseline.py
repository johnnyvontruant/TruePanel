#!/usr/bin/env python3
"""
Display the current contents of A125 character slots 0x00 through 0x07.

Uses only the documented display-write path. No CGRAM programming command is
sent.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from truepanel.lab.capture import open_controller


def main():
    slots = bytes(range(8))

    # Each slot is shown twice, making subtle shapes easier to inspect.
    payload = b"".join(
        bytes((slot, slot))
        for slot in slots
    )

    with open_controller(
        "custom-slot-baseline",
        "/dev/ttyS1",
        1200,
        1.0,
        "development/logs",
    ) as (controller, capture):
        controller.backlight(True)
        controller.clear()
        controller.write_frame(
            "SLOTS 0 1 2 3 4 5",
            payload,
        )

        input(
            "Inspect slots 0x00-0x07. "
            "Press Enter to clear..."
        )

        controller.clear()

    print("Capture:", capture)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
