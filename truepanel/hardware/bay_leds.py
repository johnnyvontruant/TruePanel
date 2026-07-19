"""
Verified QNAP TVS-671 drive-bay identify LED controller.

The controller sends one SMBus Write Byte command to address 0x33 through
the Intel I801 adapter. It performs no address scanning and no register
sweeps.
"""

from __future__ import annotations

import array
import ctypes
import errno
import fcntl
import logging
import os
import shutil
import stat
import subprocess
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any


LOGGER = logging.getLogger(__name__)

I2C_SLAVE = 0x0703
I2C_FUNCS = 0x0705
I2C_SMBUS = 0x0720

I2C_FUNC_SMBUS_WRITE_BYTE = 0x00020000
I2C_SMBUS_WRITE = 0
I2C_SMBUS_BYTE = 1

DEFAULT_DEVICE = "/dev/i2c-0"
DEFAULT_ADDRESS = 0x33
DEFAULT_LOCK_FILE = "/run/lock/truepanel-bay-led.lock"


class BayLedError(RuntimeError):
    """Raised when a guarded bay-LED operation cannot be completed."""


class _I2CSmbusData(ctypes.Union):
    _fields_ = [
        ("byte", ctypes.c_uint8),
        ("word", ctypes.c_uint16),
        ("block", ctypes.c_uint8 * 34),
    ]


class _I2CSmbusIoctlData(ctypes.Structure):
    _fields_ = [
        ("read_write", ctypes.c_uint8),
        ("command", ctypes.c_uint8),
        ("size", ctypes.c_uint32),
        ("data", ctypes.POINTER(_I2CSmbusData)),
    ]


_LIBC = ctypes.CDLL(None, use_errno=True)
_LIBC.ioctl.argtypes = [
    ctypes.c_int,
    ctypes.c_ulong,
    ctypes.c_void_p,
]
_LIBC.ioctl.restype = ctypes.c_int


def _integer(value: Any, default: int) -> int:
    if value is None:
        return default

    if isinstance(value, str):
        return int(value, 0)

    return int(value)


class SMBusByteWriter:
    """
    Send guarded SMBus Write Byte transactions.

    The character-device bridge may be loaded automatically, but loading it
    does not scan the bus or initiate any transaction.
    """

    def __init__(
        self,
        config: Mapping[str, Any] | None = None,
    ) -> None:
        settings = (
            dict(config)
            if isinstance(config, Mapping)
            else {}
        )

        self.device = str(
            settings.get("device", DEFAULT_DEVICE)
        )
        self.address = _integer(
            settings.get("address"),
            DEFAULT_ADDRESS,
        )
        self.lock_file = str(
            settings.get(
                "lock_file",
                DEFAULT_LOCK_FILE,
            )
        )
        self.load_i2c_dev = bool(
            settings.get("load_i2c_dev", True)
        )

        if not 0x03 <= self.address <= 0x77:
            raise ValueError(
                "I2C address must be between 0x03 and 0x77"
            )

    def _ensure_device(self) -> None:
        path = Path(self.device)

        try:
            mode = path.stat().st_mode
        except FileNotFoundError:
            mode = None

        if mode is not None and stat.S_ISCHR(mode):
            return

        if self.load_i2c_dev:
            modprobe = (
                shutil.which("modprobe")
                or "/sbin/modprobe"
            )

            subprocess.run(
                [modprobe, "i2c_dev"],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

        try:
            mode = path.stat().st_mode
        except FileNotFoundError as error:
            raise BayLedError(
                f"I2C adapter is unavailable: {self.device}"
            ) from error

        if not stat.S_ISCHR(mode):
            raise BayLedError(
                f"I2C adapter is not a character device: "
                f"{self.device}"
            )

    @staticmethod
    def _send_byte(
        descriptor: int,
        command: int,
    ) -> None:
        data = _I2CSmbusData()
        request = _I2CSmbusIoctlData(
            read_write=I2C_SMBUS_WRITE,
            command=command,
            size=I2C_SMBUS_BYTE,
            data=ctypes.pointer(data),
        )

        result = _LIBC.ioctl(
            descriptor,
            I2C_SMBUS,
            ctypes.byref(request),
        )

        if result < 0:
            error_number = ctypes.get_errno()

            raise BayLedError(
                "SMBus Write Byte failed: "
                f"{os.strerror(error_number)}"
            )

    def __call__(self, command: int) -> None:
        command = int(command)

        if not 0 <= command <= 0xFF:
            raise ValueError(
                "SMBus command must fit in one byte"
            )

        self._ensure_device()

        lock_descriptor = os.open(
            self.lock_file,
            os.O_CREAT
            | os.O_RDWR
            | os.O_CLOEXEC,
            0o600,
        )

        try:
            fcntl.flock(
                lock_descriptor,
                fcntl.LOCK_EX,
            )

            bus_descriptor = os.open(
                self.device,
                os.O_RDWR | os.O_CLOEXEC,
            )

            try:
                capabilities = array.array("L", [0])

                fcntl.ioctl(
                    bus_descriptor,
                    I2C_FUNCS,
                    capabilities,
                    True,
                )

                if not (
                    capabilities[0]
                    & I2C_FUNC_SMBUS_WRITE_BYTE
                ):
                    raise BayLedError(
                        "Adapter does not support "
                        "SMBus Write Byte"
                    )

                fcntl.ioctl(
                    bus_descriptor,
                    I2C_SLAVE,
                    self.address,
                )

                self._send_byte(
                    bus_descriptor,
                    command,
                )
            finally:
                os.close(bus_descriptor)
        finally:
            os.close(lock_descriptor)


class TVS671BayLedController:
    """
    Control the six verified TVS-671 bay identify LEDs.

    The physical identify channel appears as a flashing red light.
    """

    MIN_BAY = 1
    MAX_BAY = 6

    def __init__(
        self,
        config: Mapping[str, Any] | None = None,
        *,
        command_writer: Callable[[int], None] | None = None,
    ) -> None:
        self.command_writer = (
            command_writer
            or SMBusByteWriter(config)
        )
        self._states: dict[int, bool] = {}

    @classmethod
    def validate_bay(cls, bay: int) -> int:
        bay = int(bay)

        if not cls.MIN_BAY <= bay <= cls.MAX_BAY:
            raise ValueError(
                "Physical bay must be between 1 and 6"
            )

        return bay

    @classmethod
    def identify_command(
        cls,
        bay: int,
        enabled: bool,
    ) -> int:
        bay = cls.validate_bay(bay)
        on_command = bay * 2

        return (
            on_command
            if enabled
            else on_command + 1
        )

    def set_identify(
        self,
        bay: int,
        enabled: bool,
        *,
        force: bool = False,
    ) -> bool:
        bay = self.validate_bay(bay)
        enabled = bool(enabled)

        if (
            not force
            and self._states.get(bay) is enabled
        ):
            return False

        command = self.identify_command(
            bay,
            enabled,
        )

        self.command_writer(command)
        self._states[bay] = enabled

        LOGGER.info(
            "TVS-671 Bay %d identify LED %s",
            bay,
            "ON" if enabled else "OFF",
        )

        return True

    def clear_all(self) -> None:
        for bay in range(
            self.MIN_BAY,
            self.MAX_BAY + 1,
        ):
            self.set_identify(
                bay,
                False,
                force=True,
            )

    @property
    def active_bays(self) -> tuple[int, ...]:
        return tuple(
            bay
            for bay, enabled in sorted(
                self._states.items()
            )
            if enabled
        )


__all__ = [
    "BayLedError",
    "SMBusByteWriter",
    "TVS671BayLedController",
]
