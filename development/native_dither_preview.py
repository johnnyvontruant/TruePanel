#!/usr/bin/env python3
"""
Preview temporal dithering on the A125 LCD.

Alternates one candidate cell between blank (0x20) and full (0xFF) at several
frequencies and duty cycles. Uses only documented display writes.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from truepanel.lab.capture import open_controller


EMPTY = 0x20
FULL = 0xFF
WIDTH = 16


def frame_with_candidate(
    *,
    full_cells: int,
    candidate_full: bool,
) -> bytes:
    output = bytearray()

    output.extend(
        [FULL] * max(0, min(WIDTH, full_cells))
    )

    if len(output) < WIDTH:
        output.append(
            FULL if candidate_full else EMPTY
        )

    output.extend(
        [EMPTY] * (WIDTH - len(output))
    )

    return bytes(output[:WIDTH])


def run_pattern(
    controller,
    *,
    title: str,
    frequency_hz: float,
    duty_cycle: float,
    duration_seconds: float = 6.0,
    full_cells: int = 7,
) -> None:
    if frequency_hz <= 0:
        raise ValueError(
            "frequency_hz must be positive"
        )

    if not 0 < duty_cycle < 1:
        raise ValueError(
            "duty_cycle must be between zero and one"
        )

    period = 1.0 / frequency_hz
    on_time = period * duty_cycle
    off_time = period - on_time
    deadline = time.monotonic() + duration_seconds

    while time.monotonic() < deadline:
        controller.write_frame(
            title,
            frame_with_candidate(
                full_cells=full_cells,
                candidate_full=True,
            ),
        )
        time.sleep(on_time)

        controller.write_frame(
            title,
            frame_with_candidate(
                full_cells=full_cells,
                candidate_full=False,
            ),
        )
        time.sleep(off_time)


def main() -> int:
    tests = (
        ("2HZ 50%", 2.0, 0.50),
        ("4HZ 50%", 4.0, 0.50),
        ("8HZ 50%", 8.0, 0.50),
        ("4HZ 25%", 4.0, 0.25),
        ("4HZ 75%", 4.0, 0.75),
    )

    observations = []

    with open_controller(
        "native-dither-preview",
        "/dev/ttyS1",
        1200,
        1.0,
        "development/logs",
    ) as (controller, capture):
        controller.backlight(True)
        controller.clear()

        for title, frequency, duty in tests:
            print()
            print(
                f"Running {title}: "
                f"{frequency:.0f} Hz, "
                f"{duty * 100:.0f}% duty"
            )

            run_pattern(
                controller,
                title=title,
                frequency_hz=frequency,
                duty_cycle=duty,
            )

            answer = input(
                "Describe the candidate cell "
                "(smooth/flicker/dim/bright/useless/q): "
            ).strip()

            if answer.lower() == "q":
                break

            observations.append(
                (
                    title,
                    answer or "unrecorded",
                )
            )

        controller.clear()

    print()
    print("Capture:", capture)
    print("Observations:")

    for title, description in observations:
        print(
            f"  {title:<8}: {description}"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
