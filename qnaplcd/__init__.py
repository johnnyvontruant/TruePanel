#
# QNAP LCD Display and Button Class
#
import logging
from threading import Event, Thread, current_thread

import serial

from truepanel.diagnostics.protocol import (
    A125Command,
    A125Reply,
    A125Response,
    DEVICE_PREAMBLES,
    encode_backlight,
    encode_display_write,
    encode_query,
    expected_reply_payload_length,
)

# Get ID       send=0x4d, 0x00  recv=0x53, 0x01, 0xXX, 0xYY 
# Get Button   send=0x4d, 0x06  recv=0x53, 0x05, 0xXX, 0xYY
# Get Protocol send=0x4d, 0x07  recv=0x53, 0x08, 0xXX, 0xYY
# Display Char send=0x4d, 0x0C
# Display Cls  send=0x4d, 0x0D
# Backlight    send=x04d, 0x5e, 0xXX  : on,x=0x01 off,x=0x00
# Negative ACK                  recv=0x53, 0xFB, 0xXX
# Reset        send=0x4d, 0xFF

logger = logging.getLogger(__name__)


class QnapLCD:
    def __init__(self, port='/dev/ttyS1', speed=1200, handler=None):
        self.port = port
        self.speed = speed

        self.lines = 2
        self.columns = 16

        self.handler = handler
        self.reader = None
        self.stop_event = Event()

        try:
            self.connection = serial.Serial(
                self.port,
                self.speed,
                timeout=0.25,
            )
        except serial.SerialException as se:
            self.connection = None
            logger.exception("Unable to open LCD serial connection")

        if handler and self.connection:
            self.reader = Thread(
                target=self.serial_reader,
                name="qnaplcd-reader",
                daemon=True,
            )
            self.reader.start()

    def _read_bytes(self, bytes=1):
        connection = self.connection

        if not connection:
            return None

        try:
            data = connection.read(bytes)
        except (
            serial.SerialException,
            OSError,
        ):
            return None

        if not data or len(data) < bytes:
            return None

        if bytes == 1:
            return data[0]

        return data

    def _read_reply(self):
        preamble = self._read_bytes()

        if preamble is None:
            return None

        if preamble not in DEVICE_PREAMBLES:
            return None

        response = self._read_bytes()

        if response is None:
            return None

        payload_length = (
            expected_reply_payload_length(
                response
            )
        )

        if payload_length is None:
            payload = b""
        elif payload_length == 0:
            payload = b""
        else:
            payload = self._read_bytes(
                payload_length
            )

            if payload is None:
                return None

            if isinstance(payload, int):
                payload = bytes([payload])

        return A125Reply(
            preamble=preamble,
            response=response,
            payload=payload,
        )

    def _dispatch_reply(self, reply):
        if not self.handler:
            return

        response = reply.response

        if response == A125Response.BOARD_ID:
            self.handler(
                "Report_ID",
                reply.value_u16,
            )
        elif response == A125Response.BUTTON_STATUS:
            self.handler(
                "Switch_Status",
                reply.value_u16,
            )
        elif response == A125Response.PROTOCOL_VERSION:
            self.handler(
                "Protocol_Version",
                reply.value_u16,
            )
        elif response == A125Response.RESET_OK:
            self.handler("Reset_OK", True)
        elif response == A125Response.ACK:
            self.handler("Ack", None)
        elif response == A125Response.NACK:
            reason = (
                reply.payload[0]
                if reply.payload
                else None
            )
            self.handler("Nack", reason)

    def serial_reader(self):
        while not self.stop_event.is_set():
            reply = self._read_reply()

            if reply is not None:
                self._dispatch_reply(reply)

    def close(self):
        """Stop the reader thread before closing the serial connection."""

        self.stop_event.set()

        connection = self.connection
        reader = self.reader

        if connection:
            try:
                connection.cancel_read()
            except (
                AttributeError,
                serial.SerialException,
                OSError,
            ):
                pass

        if (
            reader is not None
            and reader is not current_thread()
        ):
            reader.join(timeout=1.0)

        if connection:
            try:
                connection.close()
            except (
                serial.SerialException,
                OSError,
            ):
                pass

        self.connection = None
        self.reader = None

    def backlight(self, on=True):
        if self.connection:
            self.connection.write(
                encode_backlight(on)
            )

    def clear(self):
        if self.connection:
            self.connection.write(
                encode_query(
                    A125Command.DISPLAY_CLEAR
                )
            )

    def reset(self):
        if self.connection:
            self.connection.write(
                encode_query(A125Command.RESET)
            )

    def get_board(self):
        if self.connection:
            self.connection.write(
                encode_query(
                    A125Command.GET_BOARD_ID
                )
            )

    def get_protocol(self):
        if self.connection:
            self.connection.write(
                encode_query(
                    A125Command.GET_PROTOCOL_VERSION
                )
            )

    def get_buttons(self):
        if self.connection:
            self.connection.write(
                encode_query(
                    A125Command.GET_BUTTONS
                )
            )

    def _row_address(self, line):
        # Preserve the existing driver convention:
        # logical line 1 -> row 0x00
        # logical line 2 -> row 0x01
        line %= 2
        return 0x00 if line else 0x01

    def write_bytes(self, line, payload):
        """
        Write raw character bytes to one LCD row.

        This supports LCD ROM byte values and custom-character slots without
        UTF-8 transforming the payload.
        """

        if isinstance(payload, bytearray):
            payload = bytes(payload)

        if not isinstance(payload, bytes):
            raise TypeError("payload must be bytes or bytearray")

        payload = payload[:self.columns]
        row = self._row_address(line)

        if self.connection:
            packet = encode_display_write(
                row,
                payload,
                width=self.columns,
            )

            header = packet[:4]
            encoded_payload = packet[4:]

            self.connection.write(header)
            self.connection.write(encoded_payload)
            self.connection.flush()

    def write_text(self, line, message):
        """
        Write conservative single-byte text.

        Latin-1 preserves byte values one-to-one. Unsupported characters are
        replaced instead of becoming multi-byte UTF-8 sequences.
        """

        message = str(message)[:self.columns]
        payload = message.encode("latin-1", errors="replace")
        self.write_bytes(line, payload)

    def write_frame(self, frame):
        """
        Write a two-row frame containing strings or raw byte payloads.
        """

        lines = getattr(frame, "lines", frame)

        if not isinstance(lines, (list, tuple)):
            raise TypeError("frame must provide two lines")

        first = lines[0] if len(lines) >= 1 else b""
        second = lines[1] if len(lines) >= 2 else b""

        for line_number, value in ((1, first), (2, second)):
            if isinstance(value, (bytes, bytearray)):
                self.write_bytes(line_number, value)
            else:
                self.write_text(line_number, value)

    def write(self, line, msg):
        """
        Backward-compatible text and two-line frame writer.
        """

        if isinstance(msg, list):
            self.write_frame(msg)
        elif isinstance(msg, (bytes, bytearray)):
            self.write_bytes(line, msg)
        else:
            self.write_text(line, msg)
