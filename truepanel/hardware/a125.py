"""
High-level A125 controller.

The transport object must provide:

    write(bytes)
    read(size) -> bytes
    flush()     optional

A pyserial Serial instance satisfies this contract.
"""

from __future__ import annotations
from collections import deque

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
    A125ProtocolError,
    InvalidPacket,
    UnexpectedResponse,
    UnsupportedCommand,
    encode_backlight,
    encode_display_write,
    encode_query,
    expected_reply_payload_length,
    describe_response,
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


@dataclass(frozen=True)
class A125Transaction:
    """One complete command/reply exchange with diagnostic metadata."""

    command_name: str
    response_name: str
    tx_hex: str
    rx_hex: str
    latency_ms: float
    classification: str
    expected_response: str | None = None

    def format(self) -> str:
        expected = (
            f" expected={self.expected_response}"
            if self.expected_response
            else ""
        )

        return (
            f"TX {self.tx_hex} {self.command_name} | "
            f"RX {self.rx_hex} {self.response_name} | "
            f"{self.classification}"
            f"{expected} | "
            f"{self.latency_ms:.3f} ms"
        )


class A125Controller:
    def __init__(
        self,
        transport: Any,
        timeout: float = 1.0,
    ):
        self.transport = transport
        self.timeout = float(timeout)
        self.lock = threading.RLock()

        self.last_transaction = None
        self.transaction_history = deque(maxlen=100)

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

    @staticmethod
    def _enum_name(value, enum_type=None) -> str:
        if getattr(value, "name", None):
            return value.name

        if enum_type is not None:
            try:
                return enum_type(value).name
            except (TypeError, ValueError):
                pass

        return f"0x{int(value):02X}"

    def _record_transaction(
        self,
        encoded: bytes,
        reply: A125Reply,
        started_at: float,
        expected_response=None,
    ) -> A125Transaction:
        try:
            command = A125Command(encoded[1])
            command_name = command.name
        except (ValueError, IndexError):
            command_name = (
                f"UNKNOWN_0x{encoded[1]:02X}"
                if len(encoded) > 1
                else "UNKNOWN"
            )

        response_name = self._enum_name(
            reply.response,
            A125Response,
        )
        expected_name = (
            self._enum_name(
                expected_response,
                A125Response,
            )
            if expected_response is not None
            else None
        )

        if reply.response == A125Response.NACK:
            classification = "NACK"
        elif (
            expected_response is not None
            and reply.response == expected_response
        ):
            classification = "EXPECTED"
        elif expected_response is not None:
            classification = "UNEXPECTED"
        elif reply.response == A125Response.ACK:
            classification = "ACK"
        else:
            classification = "REPLY"

        transaction = A125Transaction(
            command_name=command_name,
            response_name=response_name,
            tx_hex=" ".join(
                f"{byte:02X}" for byte in encoded
            ),
            rx_hex=reply.hex(),
            latency_ms=(
                time.perf_counter() - started_at
            ) * 1000.0,
            classification=classification,
            expected_response=expected_name,
        )

        self.last_transaction = transaction
        self.transaction_history.append(transaction)
        return transaction

    def format_last_transaction(self) -> str:
        if self.last_transaction is None:
            return "No A125 transaction recorded"

        return self.last_transaction.format()

    def exchange(
        self,
        packet: A125Packet | bytes,
        expected_response=None,
    ) -> tuple[bytes, A125Reply]:
        """
        Send one command, consume its reply, and record the transaction.
        """

        started_at = time.perf_counter()

        with self.lock:
            encoded = self.send(packet)
            reply = self.read_reply()

        self._record_transaction(
            encoded,
            reply,
            started_at,
            expected_response=expected_response,
        )

        return encoded, reply

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

    def stop_auto_display(self) -> bytes:
        packet = encode_query(
            A125Command.STOP_AUTO_DISPLAY
        )
        self.send(packet)
        return packet

    def stop_auto_display_reply(self) -> A125Reply:
        """
        Stop automatic display mode and consume the associated response.

        Some A125 firmware revisions return NACK with payload 0x28. The
        important transport requirement is that this frame belongs to the
        STOP_AUTO_DISPLAY command and must not remain queued for a later
        query.
        """

        packet = encode_query(
            A125Command.STOP_AUTO_DISPLAY
        )
        _, reply = self.exchange(packet)
        return reply

    def start_auto_display(self) -> bytes:
        packet = encode_query(
            A125Command.START_AUTO_DISPLAY
        )
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

    @staticmethod
    def _require_response(
        reply: A125Reply,
        expected: A125Response,
    ) -> None:
        """
        Validate a controller reply without discarding protocol evidence.

        NACK replies retain their reason byte and raw frame. Other recognized
        but unexpected replies are reported separately from malformed packets.
        """

        if reply.response == A125Response.NACK:
            reason = reply.payload[0] if reply.payload else None
            reason_text = (
                f"0x{reason:02X}"
                if reason is not None
                else "missing"
            )

            raise UnsupportedCommand(
                f"Controller returned NACK while expecting "
                f"{expected.name}; reason={reason_text}; "
                f"raw={reply.hex()}",
                expected_response=int(expected),
                reason=reason,
                raw_reply=reply.hex(),
            )

        if reply.response != expected:
            raise UnexpectedResponse(
                f"Expected {expected.name}, received "
                f"{describe_response(reply.response)} "
                f"(0x{reply.response:02X}); raw={reply.hex()}",
                expected_response=int(expected),
                actual_response=int(reply.response),
                raw_reply=reply.hex(),
            )

    def query_board_id(self) -> int:
        with self.lock:
            self.request_board_id()
            reply = self.read_reply()

        self._require_response(reply, A125Response.BOARD_ID)

        value = reply.value_u16

        if value is None:
            raise InvalidPacket("Invalid board ID payload")

        return value

    def query_protocol_version(self) -> int:
        with self.lock:
            self.request_protocol_version()
            reply = self.read_reply()

        self._require_response(
            reply,
            A125Response.PROTOCOL_VERSION,
        )

        value = reply.value_u16

        if value is None:
            raise InvalidPacket("Invalid protocol version payload")

        return value

    def query_buttons(self) -> int:
        with self.lock:
            started_at = time.perf_counter()
            encoded = self.request_buttons()
            reply = self.read_reply()

        self._record_transaction(
            encoded,
            reply,
            started_at,
            expected_response=A125Response.BUTTON_STATUS,
        )

        self._require_response(
            reply,
            A125Response.BUTTON_STATUS,
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
        except (TimeoutError, A125ProtocolError):
            pass

        try:
            protocol_version = self.query_protocol_version()
        except (TimeoutError, A125ProtocolError):
            pass

        return A125Capabilities(
            board_id=board_id,
            protocol_version=protocol_version,
            raw_display_bytes=True,
            custom_characters=False,
            custom_character_slots=0,
        )
