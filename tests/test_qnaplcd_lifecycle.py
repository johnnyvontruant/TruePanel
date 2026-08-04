import threading
import time

import qnaplcd


class FakeSerial:
    def __init__(
        self,
        port,
        speed,
        timeout=None,
    ):
        self.port = port
        self.speed = speed
        self.timeout = timeout
        self.closed = False
        self.cancelled = False

    def read(self, size=1):
        time.sleep(0.01)
        return b""

    def write(self, payload):
        return len(payload)

    def flush(self):
        return None

    def cancel_read(self):
        self.cancelled = True

    def close(self):
        self.closed = True


def test_reader_thread_is_daemon(
    monkeypatch,
):
    created = []

    def factory(*args, **kwargs):
        serial = FakeSerial(
            *args,
            **kwargs,
        )
        created.append(serial)
        return serial

    monkeypatch.setattr(
        qnaplcd.serial,
        "Serial",
        factory,
    )

    lcd = qnaplcd.QnapLCD(
        handler=lambda command, data: None
    )

    assert lcd.reader is not None
    assert lcd.reader.daemon is True
    assert lcd.dispatcher is not None
    assert lcd.dispatcher.daemon is True
    assert created[0].timeout == 0.25

    lcd.close()

    assert created[0].cancelled is True
    assert created[0].closed is True
    assert lcd.reader is None
    assert lcd.dispatcher is None


def test_close_without_handler(
    monkeypatch,
):
    monkeypatch.setattr(
        qnaplcd.serial,
        "Serial",
        FakeSerial,
    )

    lcd = qnaplcd.QnapLCD(
        handler=None
    )

    assert lcd.reader is None

    lcd.close()

    assert lcd.connection is None


class BlockingSerial:
    def __init__(
        self,
        port,
        speed,
        timeout=None,
    ):
        del port
        del speed
        del timeout
        self.read_started = (
            threading.Event()
        )
        self.read_released = (
            threading.Event()
        )
        self.closed = False
        self.closed_while_reading = False

    def read(self, size=1):
        del size
        self.read_started.set()
        self.read_released.wait(
            timeout=1.0
        )

        if self.closed:
            self.closed_while_reading = True

        return b""

    def write(self, payload):
        return len(payload)

    def flush(self):
        return None

    def cancel_read(self):
        self.read_released.set()

    def close(self):
        if not self.read_released.is_set():
            self.closed_while_reading = True

        self.closed = True


def test_close_joins_reader_before_serial_close(
    monkeypatch,
):
    created = []

    def factory(*args, **kwargs):
        serial = BlockingSerial(
            *args,
            **kwargs,
        )
        created.append(serial)
        return serial

    monkeypatch.setattr(
        qnaplcd.serial,
        "Serial",
        factory,
    )

    lcd = qnaplcd.QnapLCD(
        handler=lambda command, data: None
    )
    serial = created[0]

    assert serial.read_started.wait(
        timeout=1.0
    )

    lcd.close()

    assert serial.closed is True
    assert (
        serial.closed_while_reading
        is False
    )
    assert lcd.connection is None
    assert lcd.reader is None


def test_close_is_idempotent(
    monkeypatch,
):
    monkeypatch.setattr(
        qnaplcd.serial,
        "Serial",
        FakeSerial,
    )

    lcd = qnaplcd.QnapLCD(
        handler=lambda command, data: None
    )

    lcd.close()
    lcd.close()

    assert lcd.connection is None
    assert lcd.reader is None


class RecordingSerial(FakeSerial):
    def __init__(
        self,
        port,
        speed,
        timeout=None,
    ):
        super().__init__(
            port,
            speed,
            timeout=timeout,
        )
        self.writes = []
        self.flush_count = 0

    def write(self, payload):
        payload = bytes(payload)
        self.writes.append(payload)
        return len(payload)

    def flush(self):
        self.flush_count += 1


def build_recording_lcd(monkeypatch):
    created = []

    def factory(*args, **kwargs):
        connection = RecordingSerial(
            *args,
            **kwargs,
        )
        created.append(connection)
        return connection

    monkeypatch.setattr(
        qnaplcd.serial,
        "Serial",
        factory,
    )

    lcd = qnaplcd.QnapLCD(handler=None)
    return lcd, created[0]


def test_command_packets_use_a125_protocol_encoders(
    monkeypatch,
):
    lcd, connection = build_recording_lcd(
        monkeypatch
    )

    lcd.backlight(True)
    lcd.backlight(False)
    lcd.clear()
    lcd.reset()
    lcd.get_board()
    lcd.get_protocol()
    lcd.get_buttons()

    assert connection.writes == [
        b"\x4d\x5e\x01",
        b"\x4d\x5e\x00",
        b"\x4d\x0d",
        b"\x4d\xff",
        b"\x4d\x00",
        b"\x4d\x07",
        b"\x4d\x06",
    ]

    lcd.close()


def test_display_packet_preserves_legacy_write_sequence(
    monkeypatch,
):
    lcd, connection = build_recording_lcd(
        monkeypatch
    )

    lcd.write_bytes(
        1,
        b"ABC",
    )
    lcd.write_bytes(
        2,
        b"\x00\x01",
    )

    assert connection.writes == [
        b"\x4d\x0c\x00\x03",
        b"ABC",
        b"\x4d\x0c\x01\x02",
        b"\x00\x01",
    ]
    assert connection.flush_count == 2

    lcd.close()


def test_display_payload_is_truncated_to_lcd_width(
    monkeypatch,
):
    lcd, connection = build_recording_lcd(
        monkeypatch
    )

    lcd.write_bytes(
        1,
        b"1234567890ABCDEFGH",
    )

    assert connection.writes == [
        b"\x4d\x0c\x00\x10",
        b"1234567890ABCDEF",
    ]

    lcd.close()


class BufferedSerial(FakeSerial):
    def __init__(
        self,
        port,
        speed,
        timeout=None,
        payload=b"",
    ):
        super().__init__(
            port,
            speed,
            timeout=timeout,
        )
        self.buffer = bytearray(payload)

    def read(self, size=1):
        if not self.buffer:
            return b""

        output = bytes(self.buffer[:size])
        del self.buffer[:size]
        return output


def build_buffered_lcd(
    monkeypatch,
    payload,
):
    created = []

    def factory(*args, **kwargs):
        connection = BufferedSerial(
            *args,
            **kwargs,
            payload=payload,
        )
        created.append(connection)
        return connection

    monkeypatch.setattr(
        qnaplcd.serial,
        "Serial",
        factory,
    )

    lcd = qnaplcd.QnapLCD(handler=None)
    return lcd, created[0]


def test_reply_decoder_uses_authoritative_payload_lengths(
    monkeypatch,
):
    lcd, _ = build_buffered_lcd(
        monkeypatch,
        b"\x53\x05\x00\x02",
    )

    reply = lcd._read_reply()

    assert reply.preamble == 0x53
    assert reply.response == 0x05
    assert reply.payload == b"\x00\x02"
    assert reply.value_u16 == 2

    lcd.close()


def test_reply_decoder_accepts_alternate_device_preamble(
    monkeypatch,
):
    lcd, _ = build_buffered_lcd(
        monkeypatch,
        b"\x83\x08\x00\x03",
    )

    reply = lcd._read_reply()

    assert reply.preamble == 0x83
    assert reply.response == 0x08
    assert reply.value_u16 == 3

    lcd.close()


def test_reply_dispatch_preserves_legacy_callbacks(
    monkeypatch,
):
    lcd, _ = build_buffered_lcd(
        monkeypatch,
        b"",
    )
    callbacks = []
    lcd.handler = lambda command, data: (
        callbacks.append((command, data))
    )

    frames = [
        b"\x53\x01\x00\x7d",
        b"\x53\x05\x00\x02",
        b"\x53\x08\x00\x03",
        b"\x53\xaa",
        b"\x53\xfa",
        b"\x53\xfb\x28",
    ]

    for frame in frames:
        lcd.connection.buffer.extend(frame)
        reply = lcd._read_reply()
        lcd._dispatch_reply(reply)

    assert callbacks == [
        ("Report_ID", 0x007D),
        ("Switch_Status", 0x0002),
        ("Protocol_Version", 0x0003),
        ("Reset_OK", True),
        ("Ack", None),
        ("Nack", 0x28),
    ]

    lcd.close()


def test_incomplete_reply_is_not_dispatched(
    monkeypatch,
):
    lcd, _ = build_buffered_lcd(
        monkeypatch,
        b"\x53\x05\x00",
    )

    assert lcd._read_reply() is None

    lcd.close()


def test_write_helper_reports_connection_state(
    monkeypatch,
):
    lcd, connection = build_recording_lcd(
        monkeypatch
    )

    assert lcd.clear() is True
    assert connection.writes == [
        b"\x4d\x0d",
    ]

    lcd.close()

    assert lcd.clear() is False
    assert lcd.backlight(True) is False
    assert lcd.reset() is False
    assert lcd.get_board() is False
    assert lcd.get_protocol() is False
    assert lcd.get_buttons() is False
    assert lcd.write_bytes(1, b"ABC") is False


def test_write_helper_preserves_fragment_order_and_flush(
    monkeypatch,
):
    lcd, connection = build_recording_lcd(
        monkeypatch
    )

    result = lcd._write_parts(
        b"\x01\x02",
        bytearray(b"\x03\x04"),
        flush=True,
    )

    assert result is True
    assert connection.writes == [
        b"\x01\x02",
        b"\x03\x04",
    ]
    assert connection.flush_count == 1

    lcd.close()


class CoordinatedSerial(RecordingSerial):
    def __init__(
        self,
        port,
        speed,
        timeout=None,
    ):
        super().__init__(
            port,
            speed,
            timeout=timeout,
        )
        self.first_write_started = (
            threading.Event()
        )
        self.release_first_write = (
            threading.Event()
        )
        self.write_calls = 0

    def write(self, payload):
        self.write_calls += 1

        if self.write_calls == 1:
            self.first_write_started.set()
            self.release_first_write.wait(
                timeout=1.0
            )

        return super().write(payload)


def test_fragmented_display_write_is_atomic(
    monkeypatch,
):
    created = []

    def factory(*args, **kwargs):
        connection = CoordinatedSerial(
            *args,
            **kwargs,
        )
        created.append(connection)
        return connection

    monkeypatch.setattr(
        qnaplcd.serial,
        "Serial",
        factory,
    )

    lcd = qnaplcd.QnapLCD(handler=None)
    connection = created[0]

    display_thread = threading.Thread(
        target=lcd.write_bytes,
        args=(1, b"ABC"),
    )
    command_thread = threading.Thread(
        target=lcd.clear,
    )

    display_thread.start()

    assert connection.first_write_started.wait(
        timeout=1.0
    )

    command_thread.start()

    time.sleep(0.02)

    assert command_thread.is_alive()
    assert connection.writes == []

    connection.release_first_write.set()

    display_thread.join(timeout=1.0)
    command_thread.join(timeout=1.0)

    assert display_thread.is_alive() is False
    assert command_thread.is_alive() is False

    assert connection.writes == [
        b"\x4d\x0c\x00\x03",
        b"ABC",
        b"\x4d\x0d",
    ]
    assert connection.flush_count == 1

    lcd.close()


def test_disconnected_write_remains_safe_with_lock(
    monkeypatch,
):
    lcd, _ = build_recording_lcd(
        monkeypatch
    )

    lcd.close()

    results = []

    threads = [
        threading.Thread(
            target=lambda: results.append(
                lcd.clear()
            )
        )
        for _ in range(4)
    ]

    for thread in threads:
        thread.start()

    for thread in threads:
        thread.join(timeout=1.0)

    assert results == [
        False,
        False,
        False,
        False,
    ]


def test_button_reply_updates_reader_owned_cache_without_handler(
    monkeypatch,
):
    lcd, _ = build_buffered_lcd(
        monkeypatch,
        b"\x53\x05\x00\x02",
    )

    assert lcd.read_buttons() == 0

    reply = lcd._read_reply()
    lcd._dispatch_reply(reply)

    assert lcd.read_buttons() == 0x0002

    lcd.close()


def test_button_cache_and_legacy_callback_receive_same_state(
    monkeypatch,
):
    lcd, _ = build_buffered_lcd(
        monkeypatch,
        b"\x53\x05\x00\x01",
    )
    callbacks = []

    lcd.handler = lambda command, data: (
        callbacks.append((command, data))
    )

    reply = lcd._read_reply()
    lcd._dispatch_reply(reply)

    assert lcd.read_buttons() == 0x0001
    assert callbacks == [
        ("Switch_Status", 0x0001),
    ]

    lcd.close()


def test_non_button_reply_does_not_change_button_cache(
    monkeypatch,
):
    lcd, _ = build_buffered_lcd(
        monkeypatch,
        b"",
    )

    lcd.connection.buffer.extend(
        b"\x53\x05\x00\x02"
    )
    lcd._dispatch_reply(
        lcd._read_reply()
    )

    lcd.connection.buffer.extend(
        b"\x53\x08\x00\x03"
    )
    lcd._dispatch_reply(
        lcd._read_reply()
    )

    assert lcd.read_buttons() == 0x0002

    lcd.close()


def test_button_cache_is_safe_for_concurrent_polling(
    monkeypatch,
):
    lcd, _ = build_buffered_lcd(
        monkeypatch,
        b"",
    )

    observed = []

    def poll():
        for _ in range(100):
            observed.append(
                lcd.read_buttons()
            )

    threads = [
        threading.Thread(target=poll)
        for _ in range(4)
    ]

    for thread in threads:
        thread.start()

    for thread in threads:
        thread.join(timeout=1.0)

    assert len(observed) == 400
    assert set(observed) == {0}

    lcd.close()


def test_button_reports_are_queued_without_serial_polling(
    monkeypatch,
):
    lcd, _ = build_buffered_lcd(
        monkeypatch,
        b"\x53\x05\x00\x01",
    )

    reply = lcd._read_reply()
    lcd._dispatch_reply(reply)

    assert lcd.read_button_event() == 0x01
    assert lcd.read_button_event() == 0
    assert lcd.read_button_event() == 0

    lcd.close()


def test_button_event_queue_preserves_report_order(
    monkeypatch,
):
    lcd, _ = build_buffered_lcd(
        monkeypatch,
        b"",
    )

    for frame in (
        b"\x53\x05\x00\x01",
        b"\x53\x05\x00\x02",
    ):
        lcd.connection.buffer.extend(frame)
        lcd._dispatch_reply(
            lcd._read_reply()
        )

    assert [
        lcd.read_button_event(),
        lcd.read_button_event(),
        lcd.read_button_event(),
        lcd.read_button_event(),
        lcd.read_button_event(),
    ] == [
        0x01,
        0,
        0x02,
        0,
        0,
    ]

    lcd.close()


def test_zero_button_report_is_not_queued_as_press(
    monkeypatch,
):
    lcd, _ = build_buffered_lcd(
        monkeypatch,
        b"\x53\x05\x00\x00",
    )

    reply = lcd._read_reply()
    lcd._dispatch_reply(reply)

    assert lcd.read_buttons() == 0
    assert lcd.read_button_event() == 0
    assert lcd.read_button_event() == 0

    lcd.close()


def test_reader_snapshot_tracks_button_callback(
    monkeypatch,
):
    lcd, _ = build_buffered_lcd(
        monkeypatch,
        b"\x53\x05\x00\x02",
    )
    callbacks = []

    lcd.handler = lambda command, data: (
        callbacks.append((command, data))
    )

    reply = lcd._read_reply()
    lcd._dispatch_reply(reply)

    snapshot = lcd.reader_snapshot()

    assert callbacks == [
        ("Switch_Status", 0x0002),
    ]
    assert snapshot["replies"] == 1
    assert snapshot["button_reports"] == 1
    assert snapshot["last_button_mask"] == 0x0002
    assert (
        snapshot["last_pressed_button_mask"]
        == 0x0002
    )
    assert snapshot["last_button_time"] is not None
    assert snapshot["callback_count"] == 1
    assert snapshot["callback_errors"] == 0
    assert snapshot["last_callback_error"] is None
    assert (
        snapshot["last_callback_duration_ms"]
        is not None
    )
    assert snapshot["queued_button_events"] == 1

    lcd.close()


def test_callback_failure_isolated_from_reader(
    monkeypatch,
):
    lcd, _ = build_buffered_lcd(
        monkeypatch,
        b"\x53\x05\x00\x01",
    )

    def failing_handler(command, data):
        del command
        del data
        raise RuntimeError("navigation failed")

    lcd.handler = failing_handler

    reply = lcd._read_reply()

    # The callback exception must not escape and kill the reader.
    lcd._dispatch_reply(reply)

    snapshot = lcd.reader_snapshot()

    assert snapshot["replies"] == 1
    assert snapshot["button_reports"] == 1
    assert snapshot["callback_count"] == 1
    assert snapshot["callback_errors"] == 1
    assert (
        snapshot["last_callback_error"]
        == "RuntimeError: navigation failed"
    )

    lcd.close()


def test_callback_timing_tracks_maximum(
    monkeypatch,
):
    lcd, _ = build_buffered_lcd(
        monkeypatch,
        b"",
    )
    lcd.handler = lambda command, data: None

    timings = iter(
        [
            10.000,
            10.025,
            20.000,
            20.075,
        ]
    )

    monkeypatch.setattr(
        qnaplcd.time,
        "perf_counter",
        lambda: next(timings),
    )

    lcd._invoke_handler(
        "Switch_Status",
        0x01,
    )
    lcd._invoke_handler(
        "Switch_Status",
        0x02,
    )

    snapshot = lcd.reader_snapshot()

    assert snapshot["callback_count"] == 2
    assert snapshot["callback_errors"] == 0
    assert round(
        snapshot["last_callback_duration_ms"],
        3,
    ) == 75.0
    assert round(
        snapshot["max_callback_duration_ms"],
        3,
    ) == 75.0

    lcd.close()


def test_reader_snapshot_reports_thread_lifecycle(
    monkeypatch,
):
    monkeypatch.setattr(
        qnaplcd.serial,
        "Serial",
        FakeSerial,
    )

    lcd = qnaplcd.QnapLCD(
        handler=lambda command, data: None
    )

    deadline = time.monotonic() + 1.0

    while (
        lcd.reader_snapshot()["started_at"]
        is None
        and time.monotonic() < deadline
    ):
        time.sleep(0.005)

    running = lcd.reader_snapshot()

    assert running["thread_alive"] is True
    assert running["stop_requested"] is False
    assert running["started_at"] is not None
    assert running["stopped_at"] is None

    lcd.close()

    stopped = lcd.reader_snapshot()

    assert stopped["thread_alive"] is False
    assert stopped["stop_requested"] is True
    assert stopped["stopped_at"] is not None



def test_reader_snapshot_preserves_last_nonzero_button_mask(
    monkeypatch,
):
    lcd, _ = build_buffered_lcd(
        monkeypatch,
        b"",
    )

    lcd.connection.buffer.extend(
        b"\x53\x05\x00\x02"
    )
    lcd._dispatch_reply(
        lcd._read_reply()
    )

    lcd.connection.buffer.extend(
        b"\x53\x05\x00\x00"
    )
    lcd._dispatch_reply(
        lcd._read_reply()
    )

    snapshot = lcd.reader_snapshot()

    assert snapshot["last_button_mask"] == 0
    assert (
        snapshot["last_pressed_button_mask"]
        == 0x0002
    )
    assert snapshot["button_reports"] == 2

    lcd.close()



def test_production_dispatch_runs_off_reader_thread(
    monkeypatch,
):
    monkeypatch.setattr(
        qnaplcd.serial,
        "Serial",
        FakeSerial,
    )

    callback_thread_names = []
    callback_complete = threading.Event()

    def handler(command, data):
        del command
        del data
        callback_thread_names.append(
            threading.current_thread().name
        )
        callback_complete.set()

    lcd = qnaplcd.QnapLCD(
        handler=handler
    )

    lcd._dispatch_reply(
        qnaplcd.A125Reply(
            preamble=0x53,
            response=0x05,
            payload=b"\x00\x02",
        )
    )

    assert callback_complete.wait(
        timeout=1.0
    )
    assert callback_thread_names == [
        "qnaplcd-dispatcher",
    ]

    snapshot = lcd.reader_snapshot()

    assert snapshot["dispatcher_alive"] is True
    assert snapshot["dispatcher_events"] == 1
    assert snapshot["callback_count"] == 1

    lcd.close()


def test_slow_callback_does_not_block_reply_dispatch(
    monkeypatch,
):
    monkeypatch.setattr(
        qnaplcd.serial,
        "Serial",
        FakeSerial,
    )

    callback_started = threading.Event()
    release_callback = threading.Event()
    callback_finished = threading.Event()

    def handler(command, data):
        del command
        del data
        callback_started.set()
        release_callback.wait(
            timeout=1.0
        )
        callback_finished.set()

    lcd = qnaplcd.QnapLCD(
        handler=handler
    )

    first = qnaplcd.A125Reply(
        preamble=0x53,
        response=0x05,
        payload=b"\x00\x01",
    )
    second = qnaplcd.A125Reply(
        preamble=0x53,
        response=0x05,
        payload=b"\x00\x02",
    )

    lcd._dispatch_reply(first)

    assert callback_started.wait(
        timeout=1.0
    )

    started_at = time.perf_counter()
    lcd._dispatch_reply(second)
    dispatch_duration = (
        time.perf_counter() - started_at
    )

    assert dispatch_duration < 0.1

    snapshot = lcd.reader_snapshot()

    assert snapshot["replies"] == 2
    assert snapshot["button_reports"] == 2
    assert snapshot["dispatch_queue_depth"] == 1

    release_callback.set()

    assert callback_finished.wait(
        timeout=1.0
    )

    deadline = time.monotonic() + 1.0

    while (
        lcd.reader_snapshot()[
            "callback_count"
        ]
        < 2
        and time.monotonic() < deadline
    ):
        time.sleep(0.005)

    assert (
        lcd.reader_snapshot()[
            "callback_count"
        ]
        == 2
    )

    lcd.close()


def test_dispatcher_preserves_callback_order(
    monkeypatch,
):
    monkeypatch.setattr(
        qnaplcd.serial,
        "Serial",
        FakeSerial,
    )

    callbacks = []
    complete = threading.Event()

    def handler(command, data):
        callbacks.append(
            (
                command,
                data,
            )
        )

        if len(callbacks) == 4:
            complete.set()

    lcd = qnaplcd.QnapLCD(
        handler=handler
    )

    frames = [
        qnaplcd.A125Reply(
            preamble=0x53,
            response=0x05,
            payload=b"\x00\x01",
        ),
        qnaplcd.A125Reply(
            preamble=0x53,
            response=0x05,
            payload=b"\x00\x00",
        ),
        qnaplcd.A125Reply(
            preamble=0x53,
            response=0x05,
            payload=b"\x00\x02",
        ),
        qnaplcd.A125Reply(
            preamble=0x53,
            response=0x05,
            payload=b"\x00\x00",
        ),
    ]

    for frame in frames:
        lcd._dispatch_reply(frame)

    assert complete.wait(
        timeout=1.0
    )

    assert callbacks == [
        ("Switch_Status", 0x01),
        ("Switch_Status", 0x00),
        ("Switch_Status", 0x02),
        ("Switch_Status", 0x00),
    ]

    lcd.close()


def test_close_drains_queued_callback_events(
    monkeypatch,
):
    monkeypatch.setattr(
        qnaplcd.serial,
        "Serial",
        FakeSerial,
    )

    callbacks = []
    first_started = threading.Event()
    release_first = threading.Event()

    def handler(command, data):
        callbacks.append(
            (
                command,
                data,
            )
        )

        if data == 0x01:
            first_started.set()
            release_first.wait(
                timeout=1.0
            )

    lcd = qnaplcd.QnapLCD(
        handler=handler
    )

    lcd._dispatch_reply(
        qnaplcd.A125Reply(
            preamble=0x53,
            response=0x05,
            payload=b"\x00\x01",
        )
    )

    assert first_started.wait(
        timeout=1.0
    )

    lcd._dispatch_reply(
        qnaplcd.A125Reply(
            preamble=0x53,
            response=0x05,
            payload=b"\x00\x02",
        )
    )

    close_thread = threading.Thread(
        target=lcd.close
    )
    close_thread.start()

    time.sleep(0.02)

    assert close_thread.is_alive()

    release_first.set()

    close_thread.join(
        timeout=2.0
    )

    assert close_thread.is_alive() is False
    assert callbacks == [
        ("Switch_Status", 0x01),
        ("Switch_Status", 0x02),
    ]
    assert lcd.reader is None
    assert lcd.dispatcher is None


def test_dispatcher_survives_callback_failure(
    monkeypatch,
):
    monkeypatch.setattr(
        qnaplcd.serial,
        "Serial",
        FakeSerial,
    )

    callbacks = []
    complete = threading.Event()

    def handler(command, data):
        callbacks.append(data)

        if data == 0x01:
            raise RuntimeError(
                "first callback failed"
            )

        complete.set()

    lcd = qnaplcd.QnapLCD(
        handler=handler
    )

    lcd._dispatch_reply(
        qnaplcd.A125Reply(
            preamble=0x53,
            response=0x05,
            payload=b"\x00\x01",
        )
    )
    lcd._dispatch_reply(
        qnaplcd.A125Reply(
            preamble=0x53,
            response=0x05,
            payload=b"\x00\x02",
        )
    )

    assert complete.wait(
        timeout=1.0
    )

    snapshot = lcd.reader_snapshot()

    assert callbacks == [
        0x01,
        0x02,
    ]
    assert snapshot["dispatcher_alive"] is True
    assert snapshot["callback_count"] == 2
    assert snapshot["callback_errors"] == 1

    lcd.close()
