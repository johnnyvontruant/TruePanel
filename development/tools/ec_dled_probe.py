#!/usr/bin/env python3
"""
Temporarily toggle the ACPI Embedded Controller DLED bit.

EC register map:
    byte 0x78, bit 0: DLED
    byte 0x78, bit 1: PB10

The original byte is restored even if the script is interrupted.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path


EC_PATH = Path("/sys/kernel/debug/ec/ec0/io")
EC_OFFSET = 0x78
DLED_MASK = 0x01
HOLD_SECONDS = 5.0


def read_byte(fd: int, offset: int) -> int:
    data = os.pread(fd, 1, offset)

    if len(data) != 1:
        raise RuntimeError(
            f"Expected one byte from EC offset 0x{offset:02X}, "
            f"received {len(data)}."
        )

    return data[0]


def write_byte(fd: int, offset: int, value: int) -> None:
    written = os.pwrite(fd, bytes([value & 0xFF]), offset)

    if written != 1:
        raise RuntimeError(
            f"Expected to write one byte at EC offset 0x{offset:02X}, "
            f"wrote {written}."
        )

    os.fsync(fd)


def describe(label: str, value: int) -> None:
    print(
        f"{label}: EC[0x{EC_OFFSET:02X}]=0x{value:02X} "
        f"DLED={value & 1} "
        f"PB10={(value >> 1) & 1}"
    )


def main() -> int:
    if os.geteuid() != 0:
        print("Run this probe with sudo.", file=sys.stderr)
        return 1

    if not EC_PATH.exists():
        print(f"EC interface not found: {EC_PATH}", file=sys.stderr)
        return 1

    fd = os.open(EC_PATH, os.O_RDWR)
    original: int | None = None

    try:
        original = read_byte(fd, EC_OFFSET)
        toggled = original ^ DLED_MASK

        describe("Original", original)
        describe("Test    ", toggled)

        print()
        print(
            "Watch all six drive LEDs, the LCD backlight, "
            "status LEDs, and power LED."
        )
        input("Press Enter to toggle DLED for five seconds...")

        write_byte(fd, EC_OFFSET, toggled)
        observed = read_byte(fd, EC_OFFSET)
        describe("Written ", observed)

        time.sleep(HOLD_SECONDS)

    finally:
        if original is not None:
            try:
                write_byte(fd, EC_OFFSET, original)
                restored = read_byte(fd, EC_OFFSET)
                describe("Restored", restored)

                if restored != original:
                    print(
                        "WARNING: EC byte did not restore to its "
                        "original value.",
                        file=sys.stderr,
                    )
            except Exception as exc:
                print(
                    f"CRITICAL: restoration failed: {exc}",
                    file=sys.stderr,
                )

        os.close(fd)

    print()
    print("Probe complete. The original EC byte has been restored.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
