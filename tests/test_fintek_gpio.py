from __future__ import annotations

import pytest

from truepanel.hardware.fintek_gpio import (
    FINTEK_CHIP_ID,
    FINTEK_MANUFACTURER_ID,
    FintekCopyButtonReader,
)


class FakePortIO:
    def __init__(
        self,
        *,
        chip: int = FINTEK_CHIP_ID,
        manufacturer: int = FINTEK_MANUFACTURER_ID,
        enabled: int = 0x01,
        base: int = 0x0600,
        direction: int = 0x0C,
        input_value: int = 0x7F,
    ) -> None:
        self.values: dict[int, int] = {}
        self.closed = False
        self.sio_index = 0
        self.runtime_index = 0
        self.runtime_index_port = (base & 0xFFFC) + 5
        self.runtime_data_port = (base & 0xFFFC) + 6
        self.sio_registers = {
            0x20: (chip >> 8) & 0xFF,
            0x21: chip & 0xFF,
            0x23: (manufacturer >> 8) & 0xFF,
            0x24: manufacturer & 0xFF,
            0x30: enabled,
            0x60: (base >> 8) & 0xFF,
            0x61: base & 0xFF,
        }
        self.runtime_registers = {
            0x80: direction,
            0x82: input_value,
        }
        self.writes: list[tuple[int, int]] = []

    def write8(self, port: int, value: int) -> None:
        self.writes.append((port, value))
        if port == 0x2E:
            self.sio_index = value
        elif port == self.runtime_index_port:
            self.runtime_index = value
        elif port == 0x2F and self.sio_index == 0x07:
            # LDN selector write only. No mutable config field is modeled.
            pass
        elif port in (0x2F, self.runtime_data_port):
            raise AssertionError(
                f"unexpected data-register write port=0x{port:04X} "
                f"value=0x{value:02X}"
            )

    def read8(self, port: int) -> int:
        if port == 0x2F:
            return self.sio_registers.get(self.sio_index, 0)
        if port == self.runtime_data_port:
            return self.runtime_registers.get(self.runtime_index, 0)
        raise AssertionError(f"unexpected read port=0x{port:04X}")

    def close(self) -> None:
        self.closed = True


def test_reader_discovers_runtime_ports_and_reads_released_level() -> None:
    io = FakePortIO(input_value=0x7F)
    reader = FintekCopyButtonReader(io=io)

    assert reader.runtime_index_port == 0x0605
    assert reader.runtime_data_port == 0x0606
    assert reader.read_level() == 1

    io.runtime_registers[0x82] = 0x5F
    assert reader.read_level() == 0


def test_reader_rejects_unexpected_chip() -> None:
    io = FakePortIO(chip=0x1234)

    with pytest.raises(RuntimeError, match="chip id"):
        FintekCopyButtonReader(io=io)


def test_reader_rejects_unexpected_manufacturer() -> None:
    io = FakePortIO(manufacturer=0x1111)

    with pytest.raises(RuntimeError, match="manufacturer"):
        FintekCopyButtonReader(io=io)


def test_reader_rejects_disabled_gpio_ldn() -> None:
    io = FakePortIO(enabled=0)

    with pytest.raises(RuntimeError, match="disabled"):
        FintekCopyButtonReader(io=io)


@pytest.mark.parametrize("base", [0, 0xFFFF])
def test_reader_rejects_invalid_runtime_base(base: int) -> None:
    io = FakePortIO(base=base)

    with pytest.raises(RuntimeError, match="runtime base"):
        FintekCopyButtonReader(io=io)


def test_reader_rejects_gpio75_configured_as_output() -> None:
    io = FakePortIO(direction=0x2C)

    with pytest.raises(RuntimeError, match="not configured as an input"):
        FintekCopyButtonReader(io=io)


def test_reader_never_writes_gpio_direction_output_mode_or_input_data() -> None:
    io = FakePortIO()
    reader = FintekCopyButtonReader(io=io)
    reader.read_level()

    forbidden = {
        (io.runtime_data_port, 0x0C),
        (io.runtime_data_port, 0x7F),
    }
    assert not any(write in forbidden for write in io.writes)

    # Runtime access writes only the register selector, never runtime data.
    assert all(
        port != io.runtime_data_port
        for port, _ in io.writes
    )


def test_closed_reader_fails_closed() -> None:
    io = FakePortIO()
    reader = FintekCopyButtonReader(io=io)
    reader.close()

    with pytest.raises(RuntimeError, match="closed"):
        reader.read_level()