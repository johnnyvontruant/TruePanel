"""
ICP/QNAP A125 serial protocol primitives.

This module contains no serial-port code. It encodes known commands and
decodes controller replies, making the protocol independently testable.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import Iterable


HOST_PREAMBLE = 0x4D
DEVICE_PREAMBLES = (0x53, 0x83)


class A125Command(IntEnum):
    GET_BOARD_ID = 0x00
    GET_BUTTONS = 0x06
    GET_PROTOCOL_VERSION = 0x07

    DISPLAY_WRITE = 0x0C
    DISPLAY_CLEAR = 0x0D

    STOP_AUTO_DISPLAY = 0x28
    START_AUTO_DISPLAY = 0x29

    BACKLIGHT = 0x5E

    RESET = 0xFF


class A125Response(IntEnum):
    BOARD_ID = 0x01
    BUTTON_STATUS = 0x05
    PROTOCOL_VERSION = 0x08
    RESET_OK = 0xAA
    ACK = 0xFA
    NACK = 0xFB


class A125ProtocolError(ValueError):
    """Base protocol error."""


class InvalidPacket(A125ProtocolError):
    """Packet bytes do not match the documented A125 structure."""


class UnsupportedCommand(A125ProtocolError):
    """Controller returned NACK for a command."""

    def __init__(
        self,
        message: str,
        *,
        expected_response: int | None = None,
        reason: int | None = None,
        raw_reply: str | None = None,
    ):
        super().__init__(message)
        self.expected_response = expected_response
        self.reason = reason
        self.raw_reply = raw_reply


class UnexpectedResponse(A125ProtocolError):
    """Controller returned a valid but unexpected response."""

    def __init__(
        self,
        message: str,
        *,
        expected_response: int | None = None,
        actual_response: int | None = None,
        raw_reply: str | None = None,
    ):
        super().__init__(message)
        self.expected_response = expected_response
        self.actual_response = actual_response
        self.raw_reply = raw_reply


@dataclass(frozen=True)
class A125Packet:
    command: int
    payload: bytes = b""

    def __post_init__(self):
        command = int(self.command)

        if not 0 <= command <= 0xFF:
            raise InvalidPacket("Command must fit in one byte")

        payload = bytes(self.payload)

        object.__setattr__(self, "command", command)
        object.__setattr__(self, "payload", payload)

    def encode(self) -> bytes:
        return bytes([HOST_PREAMBLE, self.command]) + self.payload

    def hex(self) -> str:
        return self.encode().hex(" ").upper()


@dataclass(frozen=True)
class A125Reply:
    preamble: int
    response: int
    payload: bytes = b""

    @property
    def acknowledged(self) -> bool:
        return self.response == A125Response.ACK

    @property
    def negative_acknowledge(self) -> bool:
        return self.response == A125Response.NACK

    @property
    def value_u16(self) -> int | None:
        if len(self.payload) != 2:
            return None

        return int.from_bytes(self.payload, "big")

    def hex(self) -> str:
        return bytes(
            [self.preamble, self.response]
        ).hex(" ").upper() + (
            (" " + self.payload.hex(" ").upper())
            if self.payload
            else ""
        )


RESPONSE_PAYLOAD_LENGTHS = {
    A125Response.BOARD_ID: 2,
    A125Response.BUTTON_STATUS: 2,
    A125Response.PROTOCOL_VERSION: 2,
    A125Response.RESET_OK: 0,
    A125Response.ACK: 0,
    A125Response.NACK: 1,
}


def encode_query(command: A125Command | int) -> bytes:
    return A125Packet(int(command)).encode()


def encode_backlight(enabled: bool) -> bytes:
    return A125Packet(
        A125Command.BACKLIGHT,
        bytes([0x01 if enabled else 0x00]),
    ).encode()


def normalize_row(row: int) -> int:
    """
    Normalize logical rows to the A125 row byte.

    Accepted values:
        0 -> first row
        1 -> second row
        2 -> second row, for compatibility with existing callers
    """

    row = int(row)

    if row == 0:
        return 0x00

    if row in (1, 2):
        return 0x01

    raise InvalidPacket("LCD row must be 0, 1, or 2")


def encode_display_write(
    row: int,
    payload: bytes | bytearray | str,
    width: int = 16,
) -> bytes:
    if isinstance(payload, str):
        payload = payload.encode("latin-1", errors="replace")
    else:
        payload = bytes(payload)

    payload = payload[:width]
    row_byte = normalize_row(row)

    return A125Packet(
        A125Command.DISPLAY_WRITE,
        bytes([row_byte, len(payload)]) + payload,
    ).encode()


def expected_reply_payload_length(response: int) -> int | None:
    try:
        response = A125Response(response)
    except ValueError:
        return None

    return RESPONSE_PAYLOAD_LENGTHS.get(response)


def decode_reply(data: bytes | bytearray | Iterable[int]) -> A125Reply:
    data = bytes(data)

    if len(data) < 2:
        raise InvalidPacket("Reply must contain preamble and response")

    preamble = data[0]
    response = data[1]

    if preamble not in DEVICE_PREAMBLES:
        raise InvalidPacket(
            f"Unexpected device preamble: 0x{preamble:02X}"
        )

    expected = expected_reply_payload_length(response)

    if expected is not None and len(data) != 2 + expected:
        raise InvalidPacket(
            f"Response 0x{response:02X} requires "
            f"{expected} payload bytes, received {len(data) - 2}"
        )

    return A125Reply(
        preamble=preamble,
        response=response,
        payload=data[2:],
    )


def describe_command(command: int) -> str:
    try:
        return A125Command(command).name
    except ValueError:
        return f"UNKNOWN_0x{int(command):02X}"


def describe_response(response: int) -> str:
    try:
        return A125Response(response).name
    except ValueError:
        return f"UNKNOWN_0x{int(response):02X}"
