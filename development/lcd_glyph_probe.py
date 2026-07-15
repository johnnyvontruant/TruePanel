#!/usr/bin/env python3
"""
Probe candidate single-byte glyphs in the QNAP A125 LCD character ROM.

This uses only the documented display-write command. It does not program
CGRAM or send undocumented controller commands.
"""

import argparse
import time

import serial


PORT = "/dev/ttyS1"
SPEED = 1200

# Common custom-character, block, and extended-character candidates.
DEFAULT_CODES = [
    0x00,
    0x01,
    0x02,
    0x03,
    0x04,
    0x05,
    0x06,
    0x07,
    0x7F,
    0x80,
    0x81,
    0x82,
    0x83,
    0x84,
    0x85,
    0x86,
    0x87,
    0xA0,
    0xDB,
    0xDC,
    0xDD,
    0xDE,
    0xDF,
    0xFE,
    0xFF,
]


def write_raw(connection, row, payload):
    """Write exactly 16 raw character bytes to an A125 LCD row."""

    payload = bytes(payload[:16]).ljust(16, b" ")
    command = bytes([0x4D, 0x0C, row, len(payload)])
    connection.write(command + payload)
    connection.flush()


def write_text(connection, row, text):
    payload = text.encode("ascii", errors="replace")[:16]
    write_raw(connection, row, payload)


def clear(connection):
    connection.write(bytes([0x4D, 0x0D]))
    connection.flush()


def backlight(connection, enabled=True):
    connection.write(
        bytes([0x4D, 0x5E, 0x01 if enabled else 0x00])
    )
    connection.flush()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", default=PORT)
    parser.add_argument("--speed", type=int, default=SPEED)
    parser.add_argument("--delay", type=float, default=2.0)
    args = parser.parse_args()

    print("TruePanel LCD Glyph Probe")
    print("=========================")
    print("Watch the physical LCD.")
    print("Record codes that resemble vertical bar levels.")
    print()

    with serial.Serial(
        args.port,
        args.speed,
        timeout=1,
        write_timeout=1,
    ) as connection:
        backlight(connection, True)
        clear(connection)
        time.sleep(0.2)

        for code in DEFAULT_CODES:
            label = f"GLYPH 0x{code:02X}"
            write_text(connection, 0x00, label)
            write_raw(connection, 0x01, [code] * 16)

            print(
                f"0x{code:02X}: displaying for "
                f"{args.delay:.1f} seconds"
            )
            time.sleep(args.delay)

        write_text(connection, 0x00, "PROBE COMPLETE")
        write_text(connection, 0x01, "Restart TruePanel")

    print()
    print("Probe complete.")


if __name__ == "__main__":
    main()
