#!/usr/bin/env python3
"""
Interactive A125 LCD ROM glyph calibrator.

Each selected byte is displayed repeatedly across row two. The operator can
inspect its visual shape and record useful fill-level characters.

TruePanel must be stopped before running this tool because open_controller()
enforces exclusive serial access.
"""

from __future__ import annotations

import argparse

from truepanel.lab.capture import (
    DEFAULT_BAUD,
    DEFAULT_CAPTURE_DIR,
    DEFAULT_PORT,
    DEFAULT_TIMEOUT,
    open_controller,
)


def parse_byte(value: str) -> int:
    parsed = int(value.strip(), 0)

    if not 0 <= parsed <= 0xFF:
        raise argparse.ArgumentTypeError(
            "byte must be between 0x00 and 0xFF"
        )

    return parsed


def build_parser():
    parser = argparse.ArgumentParser(
        description=(
            "Inspect A125 LCD ROM characters through the proven "
            "raw display-byte path."
        )
    )

    parser.add_argument(
        "start",
        nargs="?",
        type=parse_byte,
        default=0x80,
        help="first ROM byte, such as 0x80",
    )
    parser.add_argument(
        "end",
        nargs="?",
        type=parse_byte,
        default=0xFF,
        help="last ROM byte, such as 0xFF",
    )
    parser.add_argument(
        "--port",
        default=DEFAULT_PORT,
    )
    parser.add_argument(
        "--baud",
        type=int,
        default=DEFAULT_BAUD,
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT,
    )
    parser.add_argument(
        "--capture-dir",
        default=str(DEFAULT_CAPTURE_DIR),
    )

    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)

    if args.start > args.end:
        raise SystemExit(
            "start byte cannot be greater than end byte"
        )

    print(
        "TruePanel ROM Glyph Calibrator\n"
        "Enter = next byte, s = save candidate, q = quit\n"
    )

    candidates = []

    with open_controller(
        "rom-level-calibration",
        args.port,
        args.baud,
        args.timeout,
        args.capture_dir,
    ) as (controller, capture):
        for value in range(
            args.start,
            args.end + 1,
        ):
            title = (
                f"ROM 0x{value:02X}"
            ).center(16)[:16]

            controller.write_frame(
                title,
                bytes([value] * 16),
            )

            response = input(
                f"0x{value:02X} "
                "[Enter/s/q]: "
            ).strip().lower()

            if response == "q":
                break

            if response == "s":
                candidates.append(value)
                print(
                    "Saved:",
                    ", ".join(
                        f"0x{item:02X}"
                        for item in candidates
                    ),
                )

        controller.write_frame(
            "ROM CAL COMPLETE",
            f"{len(candidates)} Saved",
        )

    print()
    print("Capture:", capture)
    print(
        "Candidates:",
        ", ".join(
            f"0x{value:02X}"
            for value in candidates
        )
        or "none",
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
