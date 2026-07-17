#!/usr/bin/env python3
"""
Compare hardware-supported A125 bar characters.

This tool uses only documented display writes. It shows candidate ROM
characters individually and then renders several full progress-bar styles.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from truepanel.lab.capture import open_controller


CANDIDATES = (
    ("blank", 0x20),
    ("underscore", ord("_")),
    ("dash", ord("-")),
    ("equals", ord("=")),
    ("hash", ord("#")),
    ("pipe", ord("|")),
    ("full", 0xFF),
)


def candidate_row(value: int) -> bytes:
    return bytes([value] * 16)


def mixed_bar(
    full_cells: int,
    partial: int | None = None,
) -> bytes:
    output = bytearray()

    output.extend([0xFF] * max(0, min(16, full_cells)))

    if partial is not None and len(output) < 16:
        output.append(partial)

    output.extend(
        [0x20] * (16 - len(output))
    )

    return bytes(output[:16])


def main() -> int:
    observations = []

    with open_controller(
        "rom-bar-candidate-viewer",
        "/dev/ttyS1",
        1200,
        1.0,
        "development/logs",
    ) as (controller, capture):
        controller.backlight(True)
        controller.clear()

        for name, value in CANDIDATES:
            controller.write_frame(
                f"{name[:10]:<10} 0x{value:02X}",
                candidate_row(value),
            )

            answer = input(
                f"Viewing {name} 0x{value:02X}. "
                "Describe it, Enter=skip, q=quit: "
            ).strip()

            if answer.lower() == "q":
                break

            observations.append(
                (
                    name,
                    value,
                    answer or "unrecorded",
                )
            )

        styles = (
            (
                "FULL + PIPE",
                mixed_bar(7, ord("|")),
            ),
            (
                "FULL + HASH",
                mixed_bar(7, ord("#")),
            ),
            (
                "FULL + EQUAL",
                mixed_bar(7, ord("=")),
            ),
            (
                "FULL + DASH",
                mixed_bar(7, ord("-")),
            ),
            (
                "FULL ONLY",
                mixed_bar(8),
            ),
        )

        for title, payload in styles:
            controller.write_frame(
                title,
                payload,
            )

            answer = input(
                f"Viewing {title}. "
                "useful/not useful/notes/q: "
            ).strip()

            if answer.lower() == "q":
                break

            observations.append(
                (
                    title,
                    -1,
                    answer or "unrecorded",
                )
            )

        controller.clear()

    print()
    print("Capture:", capture)
    print("Observations:")

    for name, value, description in observations:
        if value >= 0:
            print(
                f"  {name:<12} 0x{value:02X}: "
                f"{description}"
            )
        else:
            print(
                f"  {name:<12}: {description}"
            )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
