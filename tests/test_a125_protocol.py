"""
Offline tests for Project Stargate Mission 1.

Run with:

    python3 tests/test_a125_protocol.py
"""

from __future__ import annotations

import sys
from collections import deque
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from truepanel.diagnostics.protocol import (
    A125Command,
    A125Response,
    InvalidPacket,
    decode_reply,
    encode_backlight,
    encode_display_write,
    encode_query,
)
from truepanel.hardware.a125 import A125Controller


class FakeTransport:
    def __init__(self, replies=b""):
        self.writes = []
        self.replies = deque(replies)
        self.flush_count = 0

    def write(self, payload):
        self.writes.append(bytes(payload))
        return len(payload)

    def read(self, size):
        output = bytearray()

        while self.replies and len(output) < size:
            output.append(self.replies.popleft())

        return bytes(output)

    def flush(self):
        self.flush_count += 1


def test_packet_encoding():
    assert encode_query(
        A125Command.GET_BOARD_ID
    ) == bytes([0x4D, 0x00])

    assert encode_query(
        A125Command.GET_BUTTONS
    ) == bytes([0x4D, 0x06])

    assert encode_query(
        A125Command.GET_PROTOCOL_VERSION
    ) == bytes([0x4D, 0x07])

    assert encode_query(
        A125Command.DISPLAY_CLEAR
    ) == bytes([0x4D, 0x0D])

    assert encode_query(
        A125Command.RESET
    ) == bytes([0x4D, 0xFF])

    assert encode_backlight(True) == bytes(
        [0x4D, 0x5E, 0x01]
    )

    assert encode_backlight(False) == bytes(
        [0x4D, 0x5E, 0x00]
    )
    assert encode_query(
        A125Command.STOP_AUTO_DISPLAY
    ) == bytes([0x4D, 0x28])

    assert encode_query(
        A125Command.START_AUTO_DISPLAY
    ) == bytes([0x4D, 0x29])

def test_display_packets():
    assert encode_display_write(
        0,
        "HELLO",
    ) == bytes(
        [0x4D, 0x0C, 0x00, 0x05]
    ) + b"HELLO"

    assert encode_display_write(
        1,
        b"\x00\x01\x02",
    ) == bytes(
        [0x4D, 0x0C, 0x01, 0x03, 0x00, 0x01, 0x02]
    )

    long_text = "ABCDEFGHIJKLMNOPQRST"

    packet = encode_display_write(0, long_text)

    assert packet[3] == 16
    assert packet[4:] == b"ABCDEFGHIJKLMNOP"


def test_reply_decoding():
    board = decode_reply(
        bytes([0x53, 0x01, 0x12, 0x34])
    )

    assert board.response == A125Response.BOARD_ID
    assert board.value_u16 == 0x1234

    protocol = decode_reply(
        bytes([0x83, 0x08, 0x01, 0x02])
    )

    assert protocol.value_u16 == 0x0102

    ack = decode_reply(bytes([0x53, 0xFA]))

    assert ack.acknowledged

    nack = decode_reply(
        bytes([0x53, 0xFB, 0x42])
    )

    assert nack.negative_acknowledge
    assert nack.payload == b"\x42"


def test_invalid_replies():
    try:
        decode_reply(bytes([0x52, 0xFA]))
    except InvalidPacket:
        pass
    else:
        raise AssertionError("Invalid preamble was accepted")

    try:
        decode_reply(bytes([0x53, 0x01, 0x12]))
    except InvalidPacket:
        pass
    else:
        raise AssertionError("Short board ID was accepted")


def test_controller_writes():
    transport = FakeTransport()
    controller = A125Controller(transport)

    controller.clear()
    controller.stop_auto_display()
    controller.start_auto_display()
    controller.backlight(True)
    controller.write_text(0, "READY")
    controller.write_bytes(1, b"\x00\x01\x02")

    assert transport.writes == [
        bytes([0x4D, 0x0D]),
        bytes([0x4D, 0x28]),
        bytes([0x4D, 0x29]),
        bytes([0x4D, 0x5E, 0x01]),
        bytes([0x4D, 0x0C, 0x00, 0x05]) + b"READY",
        bytes(
            [0x4D, 0x0C, 0x01, 0x03, 0x00, 0x01, 0x02]
        ),
]


def test_controller_queries():
    replies = bytes(
        [
            0x53,
            0x01,
            0x12,
            0x34,
            0x53,
            0x08,
            0x01,
            0x02,
            0x53,
            0x05,
            0x00,
            0x10,
        ]
    )

    transport = FakeTransport(replies)
    controller = A125Controller(
        transport,
        timeout=0.1,
    )

    assert controller.query_board_id() == 0x1234
    assert controller.query_protocol_version() == 0x0102
    assert controller.query_buttons() == 0x0010


def run():
    tests = [
        test_packet_encoding,
        test_display_packets,
        test_reply_decoding,
        test_invalid_replies,
        test_controller_writes,
        test_controller_queries,
    ]

    for test in tests:
        test()
        print(f"PASS {test.__name__}")

    print()
    print("Project Stargate Mission 1: PASS")


if __name__ == "__main__":
    run()
