#
# QNAP LCD Display and Button Class
#
import logging
import time
from collections import deque
from queue import Queue
from threading import Event, Lock, Thread, current_thread

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
        self.dispatcher = None
        self.stop_event = Event()
        self.dispatch_queue = Queue()
        self.dispatch_stop_sentinel = object()
        self.write_lock = Lock()
        self.state_lock = Lock()
        self.button_state = 0
        self.button_events = deque()
        self.button_release_pending = False

        self.reader_started_at = None
        self.reader_stopped_at = None
        self.reader_replies = 0
        self.reader_errors = 0
        self.last_reader_error = None

        self.dispatcher_started_at = None
        self.dispatcher_stopped_at = None
        self.dispatcher_events = 0

        self.button_reports = 0
        self.last_button_mask = 0
        self.last_pressed_button_mask = 0
        self.last_button_time = None

        self.callback_count = 0
        self.callback_errors = 0
        self.last_callback_error = None
        self.last_callback_duration_ms = None
        self.max_callback_duration_ms = 0.0

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
            self.dispatcher = Thread(
                target=self.event_dispatcher,
                name="qnaplcd-dispatcher",
                daemon=True,
            )
            self.dispatcher.start()

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

    def _invoke_handler(self, command, data):
        if not self.handler:
            return

        started_at = time.perf_counter()

        try:
            self.handler(command, data)
        except Exception as exc:
            duration_ms = (
                time.perf_counter() - started_at
            ) * 1000.0

            with self.state_lock:
                self.callback_count += 1
                self.callback_errors += 1
                self.last_callback_error = (
                    f"{type(exc).__name__}: {exc}"
                )
                self.last_callback_duration_ms = (
                    duration_ms
                )
                self.max_callback_duration_ms = max(
                    self.max_callback_duration_ms,
                    duration_ms,
                )

            logger.exception(
                "LCD callback failed: command=%s data=%r",
                command,
                data,
            )
            return

        duration_ms = (
            time.perf_counter() - started_at
        ) * 1000.0

        with self.state_lock:
            self.callback_count += 1
            self.last_callback_error = None
            self.last_callback_duration_ms = (
                duration_ms
            )
            self.max_callback_duration_ms = max(
                self.max_callback_duration_ms,
                duration_ms,
            )

        if duration_ms >= 100.0:
            logger.warning(
                (
                    "Slow LCD callback: "
                    "command=%s duration_ms=%.3f"
                ),
                command,
                duration_ms,
            )

    def submit_button_event(
        self,
        button_mask,
        *,
        source="web",
    ):
        """
        Submit one validated virtual button press to the event dispatcher.

        This does not write serial data or imitate an A125 reply. It places
        the same logical Switch_Status event used by physical button reports
        onto the existing ordered callback queue.
        """

        try:
            button_mask = int(
                button_mask
            )
        except (
            TypeError,
            ValueError,
        ):
            return False

        if button_mask not in {
            0x01,
            0x02,
        }:
            return False

        if source != "web":
            return False

        dispatcher = self.dispatcher

        if (
            dispatcher is None
            or not dispatcher.is_alive()
            or self.stop_event.is_set()
        ):
            return False

        self._queue_handler_event(
            "Switch_Status",
            button_mask,
        )

        logger.info(
            (
                "Virtual LCD button queued: "
                "source=%s mask=0x%04X"
            ),
            source,
            button_mask,
        )

        return True


    def _queue_handler_event(self, command, data):
        """
        Queue one decoded callback event for ordered delivery.

        Tests and compatibility callers that attach a handler after
        construction retain synchronous delivery when no dispatcher thread
        exists. Production construction starts the dedicated dispatcher.
        """

        dispatcher = self.dispatcher

        if (
            dispatcher is None
            or not dispatcher.is_alive()
        ):
            self._invoke_handler(
                command,
                data,
            )
            return

        self.dispatch_queue.put(
            (
                command,
                data,
            )
        )

    def event_dispatcher(self):
        with self.state_lock:
            self.dispatcher_started_at = time.time()
            self.dispatcher_stopped_at = None

        logger.info(
            "QNAP LCD event dispatcher started"
        )

        try:
            while True:
                event = self.dispatch_queue.get()

                try:
                    if event is self.dispatch_stop_sentinel:
                        return

                    command, data = event

                    with self.state_lock:
                        self.dispatcher_events += 1

                    self._invoke_handler(
                        command,
                        data,
                    )
                finally:
                    self.dispatch_queue.task_done()
        finally:
            with self.state_lock:
                self.dispatcher_stopped_at = time.time()

            logger.info(
                "QNAP LCD event dispatcher stopped"
            )

    def _dispatch_reply(self, reply):
        response = reply.response
        command = None
        data = None

        with self.state_lock:
            self.reader_replies += 1

        if response == A125Response.BUTTON_STATUS:
            value = reply.value_u16

            if value is not None:
                with self.state_lock:
                    self.button_state = value
                    self.button_reports += 1
                    self.last_button_mask = value
                    self.last_button_time = time.time()

                    if value:
                        self.last_pressed_button_mask = value
                        self.button_events.append(
                            value
                        )

            command = "Switch_Status"
            data = value

            logger.debug(
                "A125 button report: mask=0x%04X",
                value or 0,
            )
        elif response == A125Response.BOARD_ID:
            command = "Report_ID"
            data = reply.value_u16
        elif response == A125Response.PROTOCOL_VERSION:
            command = "Protocol_Version"
            data = reply.value_u16
        elif response == A125Response.RESET_OK:
            command = "Reset_OK"
            data = True
        elif response == A125Response.ACK:
            command = "Ack"
        elif response == A125Response.NACK:
            command = "Nack"
            data = (
                reply.payload[0]
                if reply.payload
                else None
            )

        if command is not None:
            self._queue_handler_event(
                command,
                data,
            )

    def serial_reader(self):
        with self.state_lock:
            self.reader_started_at = time.time()
            self.reader_stopped_at = None
            self.last_reader_error = None

        logger.info(
            "QNAP LCD reader started on %s at %s baud",
            self.port,
            self.speed,
        )

        try:
            while not self.stop_event.is_set():
                try:
                    reply = self._read_reply()

                    if reply is not None:
                        self._dispatch_reply(reply)
                except Exception as exc:
                    with self.state_lock:
                        self.reader_errors += 1
                        self.last_reader_error = (
                            f"{type(exc).__name__}: {exc}"
                        )

                    logger.exception(
                        "Unexpected QNAP LCD reader failure"
                    )

                    if not self.stop_event.is_set():
                        time.sleep(0.05)
        finally:
            with self.state_lock:
                self.reader_stopped_at = time.time()

            logger.info(
                "QNAP LCD reader stopped"
            )

    def reader_snapshot(self):
        """
        Return a thread-safe diagnostic snapshot without serial I/O.
        """

        with self.state_lock:
            reader = self.reader
            dispatcher = self.dispatcher

            return {
                "thread_alive": bool(
                    reader is not None
                    and reader.is_alive()
                ),
                "dispatcher_alive": bool(
                    dispatcher is not None
                    and dispatcher.is_alive()
                ),
                "stop_requested": (
                    self.stop_event.is_set()
                ),
                "started_at": self.reader_started_at,
                "stopped_at": self.reader_stopped_at,
                "dispatcher_started_at": (
                    self.dispatcher_started_at
                ),
                "dispatcher_stopped_at": (
                    self.dispatcher_stopped_at
                ),
                "dispatcher_events": (
                    self.dispatcher_events
                ),
                "dispatch_queue_depth": (
                    self.dispatch_queue.qsize()
                ),
                "replies": self.reader_replies,
                "reader_errors": self.reader_errors,
                "last_reader_error": self.last_reader_error,
                "button_reports": self.button_reports,
                "last_button_mask": self.last_button_mask,
                "last_pressed_button_mask": (
                    self.last_pressed_button_mask
                ),
                "last_button_time": self.last_button_time,
                "callback_count": self.callback_count,
                "callback_errors": self.callback_errors,
                "last_callback_error": (
                    self.last_callback_error
                ),
                "last_callback_duration_ms": (
                    self.last_callback_duration_ms
                ),
                "max_callback_duration_ms": (
                    self.max_callback_duration_ms
                ),
                "queued_button_events": len(
                    self.button_events
                ),
            }

    def read_buttons(self):
        """
        Return the latest button mask received by the background reader.

        This compatibility method performs no serial I/O. Event-oriented
        consumers should use read_button_event() so each controller report is
        consumed exactly once.
        """

        with self.state_lock:
            return self.button_state

    def read_button_event(self):
        """
        Convert queued A125 button reports into pollable press/release pulses.

        Each nonzero controller report is returned exactly once. The following
        read returns zero to provide a synthetic release sample. Incoming A125
        frames remain owned exclusively by the background reader.
        """

        with self.state_lock:
            if self.button_release_pending:
                self.button_release_pending = False
                return 0

            if not self.button_events:
                return 0

            self.button_release_pending = True
            return self.button_events.popleft()

    def close(self):
        """
        Stop the reader and dispatcher before closing the serial connection.

        The reader stops first so no new callback events can be queued. The
        sentinel is then placed behind any already-decoded events, allowing
        the dispatcher to drain them in order before exiting.
        """

        self.stop_event.set()

        connection = self.connection
        reader = self.reader
        dispatcher = self.dispatcher

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

        if (
            dispatcher is not None
            and dispatcher.is_alive()
        ):
            self.dispatch_queue.put(
                self.dispatch_stop_sentinel
            )

        if (
            dispatcher is not None
            and dispatcher is not current_thread()
        ):
            dispatcher.join(timeout=2.0)

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
        self.dispatcher = None

    def _write_parts(self, *parts, flush=False):
        """
        Write one or more packet fragments to the active transport.

        The legacy driver deliberately keeps display headers and payloads as
        separate writes. Centralizing transport access preserves that behavior
        while giving future lifecycle and diagnostic work one guarded path.
        """

        with self.write_lock:
            connection = self.connection

            if not connection:
                return False

            for part in parts:
                connection.write(bytes(part))

            if flush:
                connection.flush()

        return True

    def backlight(self, on=True):
        return self._write_parts(
            encode_backlight(on)
        )

    def clear(self):
        return self._write_parts(
            encode_query(
                A125Command.DISPLAY_CLEAR
            )
        )

    def reset(self):
        return self._write_parts(
            encode_query(A125Command.RESET)
        )

    def get_board(self):
        return self._write_parts(
            encode_query(
                A125Command.GET_BOARD_ID
            )
        )

    def get_protocol(self):
        return self._write_parts(
            encode_query(
                A125Command.GET_PROTOCOL_VERSION
            )
        )

    def get_buttons(self):
        return self._write_parts(
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

        packet = encode_display_write(
            row,
            payload,
            width=self.columns,
        )

        header = packet[:4]
        encoded_payload = packet[4:]

        return self._write_parts(
            header,
            encoded_payload,
            flush=True,
        )

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
        Write a two-row frame as one guarded transport transaction.

        Both display packets share one write lock and one final flush. This
        keeps frames atomic, avoids per-row flush overhead, and prevents other
        LCD operations from being interleaved between the two rows.
        """

        lines = getattr(frame, "lines", frame)

        if not isinstance(lines, (list, tuple)):
            raise TypeError("frame must provide two lines")

        first = lines[0] if len(lines) >= 1 else b""
        second = lines[1] if len(lines) >= 2 else b""

        packets = []

        for line_number, value in ((1, first), (2, second)):
            if isinstance(value, bytearray):
                value = bytes(value)

            if isinstance(value, bytes):
                payload = value[:self.columns]
            else:
                payload = (
                    str(value)[:self.columns]
                    .encode(
                        "latin-1",
                        errors="replace",
                    )
                )

            row = self._row_address(
                line_number
            )
            packet = encode_display_write(
                row,
                payload,
                width=self.columns,
            )

            packets.extend(
                [
                    packet[:4],
                    packet[4:],
                ]
            )

        return self._write_parts(
            *packets,
            flush=True,
        )

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
