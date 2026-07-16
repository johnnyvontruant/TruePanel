#!/usr/bin/env python3
"""
Narrow A125 command-response probe.

Sends only explicitly listed two-byte command headers and records whether the
controller returns ACK, NACK, another response, or no reply. The reset opcode
is forbidden and cannot be selected.
"""

from __future__ import annotations

import select
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from truepanel.lab.capture import open_controller


CANDIDATES = (
    0x08,
    0x09,
    0x0A,
    0x0B,
    0x0E,
    0x0F,
    0x10,
)

FORBIDDEN = {
    0xFF,
}


def read_available(transport, timeout=0.35):
    """
    Read through CaptureTransport so RX bytes are preserved in the log.
    """

    connection = getattr(
        transport,
        "transport",
        transport,
    )

    deadline = time.monotonic() + timeout
    result = bytearray()

    while time.monotonic() < deadline:
        ready, _, _ = select.select(
            [connection],
            [],
            [],
            0.05,
        )

        if not ready:
            continue

        chunk = transport.read(64)

        if chunk:
            result.extend(chunk)

    return bytes(result)


def describe(payload):
    if not payload:
        return "NO RESPONSE"

    text = payload.hex(" ").upper()

    if len(payload) >= 2 and payload[0] in (0x53, 0x83):
        response = payload[1]

        if response == 0xFA:
            return f"ACK {text}"

        if response == 0xFB:
            rejected = (
                f" rejected=0x{payload[2]:02X}"
                if len(payload) >= 3
                else ""
            )
            return f"NACK {text}{rejected}"

    return f"OTHER {text}"


def main():
    observations = []

    with open_controller(
        "a125-command-response-probe",
        "/dev/ttyS1",
        1200,
        0.35,
        "development/logs",
    ) as (controller, capture):
        controller.backlight(True)
        controller.clear()

        transport = controller.transport

        for opcode in CANDIDATES:
            if opcode in FORBIDDEN:
                raise RuntimeError(
                    f"Forbidden opcode selected: 0x{opcode:02X}"
                )

            controller.write_frame(
                f"PROBE 0x{opcode:02X}",
                "Awaiting command",
            )

            print()
            print(f"Candidate opcode 0x{opcode:02X}")
            answer = input(
                "Press Enter to transmit, s to skip, q to quit: "
            ).strip().lower()

            if answer == "q":
                break

            if answer == "s":
                continue

            controller.send(
                bytes((0x4D, opcode))
            )

            response = read_available(
                transport,
            )
            result = describe(response)

            observations.append(
                (opcode, result)
            )

            print(result)

            controller.clear()
            time.sleep(0.15)

        controller.clear()

    print()
    print("Capture:", capture)
    print("Results:")

    for opcode, result in observations:
        print(
            f"  0x{opcode:02X}: {result}"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
