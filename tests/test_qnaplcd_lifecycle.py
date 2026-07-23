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
    assert created[0].timeout == 0.25

    lcd.close()

    assert created[0].cancelled is True
    assert created[0].closed is True
    assert lcd.reader is None


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
