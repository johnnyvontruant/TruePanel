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
