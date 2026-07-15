"""
Interactive A125 character-ROM glyph probe.

Displays one raw byte repeatedly on row 1 while showing its hexadecimal
value on row 2. Only the documented DISPLAY_WRITE and BACKLIGHT commands
are used.
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
    result = int(value, 0)

    if not 0 <= result <= 0xFF:
        raise argparse.ArgumentTypeError(
            "byte must be between 0x00 and 0xFF"
        )

    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Interactive A125 glyph probe"
    )
    parser.add_argument(
        "--start",
        type=parse_byte,
        default=0x00,
    )
    parser.add_argument(
        "--end",
        type=parse_byte,
        default=0xFF,
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


def main() -> int:
    args = build_parser().parse_args()

    if args.start > args.end:
        raise SystemExit("--start must not exceed --end")

    with open_controller(
        "glyph-level-probe",
        args.port,
        args.baud,
        args.timeout,
        args.capture_dir,
    ) as (controller, capture):
        controller.backlight(True)

        for value in range(args.start, args.end + 1):
            controller.write_frame(
                bytes([value]) * 16,
                f"BYTE 0x{value:02X}",
            )

            answer = input(
                f"0x{value:02X}: "
                "Enter=next, s=save candidate, q=quit: "
            ).strip().lower()

            if answer == "s":
                print(f"CANDIDATE 0x{value:02X}")

            if answer == "q":
                break

        print(f"Capture: {capture}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
