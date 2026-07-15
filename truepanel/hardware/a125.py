"""
High-level A125 controller.

The transport object must provide:

    write(bytes)
    read(size) -> bytes
    flush()     optional

A pyserial Serial instance satisfies this contract.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Any

from truepanel.diagnostics.protocol import (
    A125Command,
    A125Packet,
    A125Reply,
    A125Response,
    DEVICE_PREAMBLES,
    InvalidPacket,
    encode_backlight,
    encode_display_write,
    encode_query,
    expected_reply_payload_length,
)


@dataclass(frozen=True)
class A125Capabilities:
    board_id: int | None = None
    protocol_version: int | None = None
    raw_display_bytes: bool = True
    custom_characters: bool = False
    custom_character_slots: int = 0

    @property
    def graphics_mode(self) -> str:
        if self.custom_characters:
            return "custom"

        if self.raw_display_bytes:
            return "raw"

        return "ascii"


class A125Controller:
    def __init__(
        self,
        transport: Any,
        timeout: float = 1.0,
    ):
        self.transport = transport
        self.timeout = float(timeout)
        self.lock = threading.RLock()

    def _flush(self):
        flush = getattr(self.transport, "flush", None)

        if callable(flush):
            flush()

    def send(self, packet: A125Packet | bytes) -> bytes:
        encoded = (
            packet.encode()
            if isinstance(packet, A125Packet)
            else bytes(packet)
        )

        with self.lock:
            self.transport.write(encoded)
            self._flush()

        return encoded

    def write_bytes(self, row: int, payload: bytes) -> bytes:
        packet = encode_display_write(row, payload)
        self.send(packet)
        return packet

    def write_text(self, row: int, text: str) -> bytes:
        packet = encode_display_write(row, text)
        self.send(packet)
        return packet

    def write_frame(self, line1, line2) -> None:
        if isinstance(line1, str):
            self.write_text(0, line1)
        else:
            self.write_bytes(0, bytes(line1))

        if isinstance(line2, str):
            self.write_text(1, line2)
        else:
            self.write_bytes(1, bytes(line2))

    def clear(self) -> bytes:
        packet = encode_query(A125Command.DISPLAY_CLEAR)
        self.send(packet)
        return packet

    def reset(self) -> bytes:
        packet = encode_query(A125Command.RESET)
        self.send(packet)
        return packet

    def backlight(self, enabled=True) -> bytes:
        packet = encode_backlight(enabled)
        self.send(packet)
        return packet

    def request_board_id(self) -> bytes:
        packet = encode_query(A125Command.GET_BOARD_ID)
        self.send(packet)
        return packet

    def request_protocol_version(self) -> bytes:
        packet = encode_query(A125Command.GET_PROTOCOL_VERSION)
        self.send(packet)
        return packet

    def request_buttons(self) -> bytes:
        packet = encode_query(A125Command.GET_BUTTONS)
        self.send(packet)
        return packet

    def _read_exact(self, size: int) -> bytes:
        deadline = time.monotonic() + self.timeout
        output = bytearray()

        while len(output) < size:
            if time.monotonic() >= deadline:
                raise TimeoutError(
                    f"Timed out reading {size} A125 bytes"
                )

            chunk = self.transport.read(size - len(output))

            if chunk:
                output.extend(chunk)
            else:
                time.sleep(0.005)

        return bytes(output)

    def read_reply(self) -> A125Reply:
        """
        Read one complete reply from the controller.

        Unknown responses are returned with no assumed payload. Known replies
        use the documented payload lengths.
        """

        while True:
            preamble = self._read_exact(1)[0]

            if preamble in DEVICE_PREAMBLES:
                break

        response = self._read_exact(1)[0]
        payload_length = expected_reply_payload_length(response)

        if payload_length is None:
            payload = b""
        else:
            payload = self._read_exact(payload_length)

        return A125Reply(
            preamble=preamble,
            response=response,
            payload=payload,
        )

    def query_board_id(self) -> int:
        with self.lock:
            self.request_board_id()
            reply = self.read_reply()

        if reply.response != A125Response.BOARD_ID:
            raise InvalidPacket(
                f"Expected BOARD_ID, received 0x{reply.response:02X}"
            )

        value = reply.value_u16

        if value is None:
            raise InvalidPacket("Invalid board ID payload")

        return value

    def query_protocol_version(self) -> int:
        with self.lock:
            self.request_protocol_version()
            reply = self.read_reply()

        if reply.response != A125Response.PROTOCOL_VERSION:
            raise InvalidPacket(
                "Expected PROTOCOL_VERSION, received "
                f"0x{reply.response:02X}"
            )

        value = reply.value_u16

        if value is None:
            raise InvalidPacket("Invalid protocol version payload")

        return value

    def query_buttons(self) -> int:
        with self.lock:
            self.request_buttons()
            reply = self.read_reply()

        if reply.response != A125Response.BUTTON_STATUS:
            raise InvalidPacket(
                "Expected BUTTON_STATUS, received "
                f"0x{reply.response:02X}"
            )

        value = reply.value_u16

        if value is None:
            raise InvalidPacket("Invalid button payload")

        return value

    def detect_capabilities(self) -> A125Capabilities:
        board_id = None
        protocol_version = None

        try:
            board_id = self.query_board_id()
        except (TimeoutError, InvalidPacket):
            pass

        try:
            protocol_version = self.query_protocol_version()
        except (TimeoutError, InvalidPacket):
            pass

        return A125Capabilities(
            board_id=board_id,
            protocol_version=protocol_version,
            raw_display_bytes=True,
            custom_characters=False,
            custom_character_slots=0,
        )
