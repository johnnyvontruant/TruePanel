from pathlib import Path

import pytest

from truepanel.lab import capture as capture_module


class FakeSerial:
    instances = []

    def __init__(
        self,
        port,
        baud,
        *,
        timeout,
        write_timeout,
    ):
        self.port = port
        self.baud = baud
        self.timeout = timeout
        self.write_timeout = write_timeout
        self.writes = []
        self.closed = False

        self.__class__.instances.append(self)

    def write(self, payload):
        payload = bytes(payload)
        self.writes.append(payload)
        return len(payload)

    def read(self, size):
        return b""

    def flush(self):
        return None

    def close(self):
        self.closed = True


class FakeSerialModule:
    Serial = FakeSerial


@pytest.fixture(autouse=True)
def reset_serial_instances():
    FakeSerial.instances.clear()


@pytest.fixture
def patched_environment(
    monkeypatch,
    tmp_path,
):
    device = tmp_path / "ttyS1"
    device.touch()

    monkeypatch.setattr(
        capture_module,
        "require_exclusive_access",
        lambda: None,
    )
    monkeypatch.setattr(
        capture_module.os.path,
        "exists",
        lambda path: True,
    )

    monkeypatch.setitem(
        __import__("sys").modules,
        "serial",
        FakeSerialModule(),
    )

    return device


def test_open_controller_claims_and_restores_display(
    patched_environment,
    tmp_path,
):
    with capture_module.open_controller(
        "ownership-test",
        port=str(patched_environment),
        capture_dir=tmp_path,
    ) as (controller, path):
        controller.write_frame(
            "LAB ACTIVE",
            "TESTING",
        )

    connection = FakeSerial.instances[0]

    assert connection.writes == [
        b"\x4D\x28",
        b"\x4D\x0C\x00\x0A"
        b"LAB ACTIVE",
        b"\x4D\x0C\x01\x07"
        b"TESTING",
        b"\x4D\x0D",
        b"\x4D\x29",
    ]
    assert connection.closed is True
    assert path.exists()


def test_open_controller_restores_after_error(
    patched_environment,
    tmp_path,
):
    with pytest.raises(
        RuntimeError,
        match="experiment exploded",
    ):
        with capture_module.open_controller(
            "failure-test",
            port=str(patched_environment),
            capture_dir=tmp_path,
        ):
            raise RuntimeError(
                "experiment exploded"
            )

    connection = FakeSerial.instances[0]

    assert connection.writes == [
        b"\x4D\x28",
        b"\x4D\x0D",
        b"\x4D\x29",
    ]
    assert connection.closed is True
