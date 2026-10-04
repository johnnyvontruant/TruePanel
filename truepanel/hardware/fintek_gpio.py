"""Read-only Fintek GPIO access for the verified TVS-671 Copy button."""

from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Protocol

FINTEK_CHIP_ID = 0x1007
FINTEK_MANUFACTURER_ID = 0x1934
FINTEK_GPIO_LDN = 0x06

SIO_INDEX_PORT = 0x2E
SIO_DATA_PORT = 0x2F
SIO_UNLOCK = 0x87
SIO_LOCK = 0xAA
SIO_LDN_REGISTER = 0x07

GPIO7_DIRECTION_REGISTER = 0x80
GPIO7_INPUT_REGISTER = 0x82
COPY_BUTTON_BIT = 5


class PortIO(Protocol):
    def read8(self, port: int) -> int: ...

    def write8(self, port: int, value: int) -> None: ...

    def close(self) -> None: ...


class DevPortIO:
    """Minimal /dev/port byte I/O adapter."""

    def __init__(self, path: Path = Path("/dev/port")) -> None:
        self.path = Path(path)
        self._fd = os.open(
            self.path,
            os.O_RDWR | os.O_SYNC,
        )

    def read8(self, port: int) -> int:
        payload = os.pread(self._fd, 1, int(port))
        if len(payload) != 1:
            raise OSError(f"short /dev/port read at 0x{port:04X}")
        return payload[0]

    def write8(self, port: int, value: int) -> None:
        written = os.pwrite(
            self._fd,
            bytes((int(value) & 0xFF,)),
            int(port),
        )
        if written != 1:
            raise OSError(f"short /dev/port write at 0x{port:04X}")

    def close(self) -> None:
        os.close(self._fd)


class FintekCopyButtonReader:
    """Read GPIO75 through the Fintek runtime GPIO register window.

    Construction performs a read-only identity/configuration probe through the
    Super-I/O selector ports. It writes only selector/unlock/lock bytes, never a
    GPIO direction, output, mode, or other configuration value. Steady-state
    button reads use the runtime GPIO index/data ports discovered from CR60/61.
    """

    def __init__(
        self,
        io: PortIO | None = None,
    ) -> None:
        self._io = io or DevPortIO()
        self._owns_io = io is None
        self._lock = threading.Lock()
        self._closed = False
        self._runtime_index = 0
        self._runtime_data = 0

        try:
            self._initialize()
        except Exception:
            if self._owns_io:
                self._io.close()
            raise

    def _sio_reg(self, register: int) -> int:
        self._io.write8(SIO_INDEX_PORT, register)
        return self._io.read8(SIO_DATA_PORT)

    def _sio_word(self, register: int) -> int:
        high = self._sio_reg(register)
        low = self._sio_reg((register + 1) & 0xFF)
        return (high << 8) | low

    def _runtime_reg(self, register: int) -> int:
        self._io.write8(self._runtime_index, register)
        return self._io.read8(self._runtime_data)

    def _initialize(self) -> None:
        with self._lock:
            self._io.write8(SIO_INDEX_PORT, SIO_UNLOCK)
            self._io.write8(SIO_INDEX_PORT, SIO_UNLOCK)
            try:
                chip = self._sio_word(0x20)
                manufacturer = self._sio_word(0x23)

                if chip != FINTEK_CHIP_ID:
                    raise RuntimeError(
                        f"unexpected Fintek chip id 0x{chip:04X}"
                    )
                if manufacturer != FINTEK_MANUFACTURER_ID:
                    raise RuntimeError(
                        "unexpected Fintek manufacturer "
                        f"0x{manufacturer:04X}"
                    )

                self._io.write8(
                    SIO_INDEX_PORT,
                    SIO_LDN_REGISTER,
                )
                self._io.write8(
                    SIO_DATA_PORT,
                    FINTEK_GPIO_LDN,
                )

                enabled = self._sio_reg(0x30)
                base = self._sio_word(0x60)
            finally:
                self._io.write8(
                    SIO_INDEX_PORT,
                    SIO_LOCK,
                )

            if not enabled & 0x01:
                raise RuntimeError("Fintek GPIO logical device is disabled")
            if base in (0, 0xFFFF):
                raise RuntimeError("Fintek GPIO runtime base is invalid")

            runtime_base = base & 0xFFFC
            self._runtime_index = runtime_base + 5
            self._runtime_data = runtime_base + 6

            direction = self._runtime_reg(
                GPIO7_DIRECTION_REGISTER
            )
            if direction & (1 << COPY_BUTTON_BIT):
                raise RuntimeError(
                    "GPIO75 is not configured as an input"
                )

    @property
    def runtime_index_port(self) -> int:
        return self._runtime_index

    @property
    def runtime_data_port(self) -> int:
        return self._runtime_data

    def read_level(self) -> int:
        """Return GPIO75 electrical level: 0 pressed, 1 released."""
        with self._lock:
            if self._closed:
                raise RuntimeError("Fintek Copy button reader is closed")

            value = self._runtime_reg(GPIO7_INPUT_REGISTER)
            return 1 if value & (1 << COPY_BUTTON_BIT) else 0

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            if self._owns_io:
                self._io.close()

    def __enter__(self) -> "FintekCopyButtonReader":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()


__all__ = [
    "COPY_BUTTON_BIT",
    "DevPortIO",
    "FINTEK_CHIP_ID",
    "FINTEK_GPIO_LDN",
    "FINTEK_MANUFACTURER_ID",
    "FintekCopyButtonReader",
    "GPIO7_DIRECTION_REGISTER",
    "GPIO7_INPUT_REGISTER",
]