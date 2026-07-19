"""
Capture and serial-controller utilities for Project Stargate.

This module owns laboratory serial access, exclusive-port protection, and
human-readable TX/RX capture logging. It contains no CLI argument parsing.
"""

from __future__ import annotations

import os
import subprocess
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Iterator

from truepanel.hardware.a125 import A125Controller


DEFAULT_PORT = "/dev/ttyS1"
DEFAULT_BAUD = 1200
DEFAULT_TIMEOUT = 1.0
DEFAULT_CAPTURE_DIR = Path("development/logs")


def service_is_active(service: str = "truepanel") -> bool:
    """Return True when the named systemd service is active."""

    result = subprocess.run(
        ["systemctl", "is-active", "--quiet", service],
        check=False,
    )
    return result.returncode == 0


def require_exclusive_access(service: str = "truepanel") -> None:
    """Refuse laboratory access while TruePanel owns the serial port."""

    if service_is_active(service):
        raise RuntimeError(
            f"{service}.service is running. Run:\n"
            f"  systemctl stop {service}\n"
            "before using the Stargate Laboratory."
        )


def build_capture_path(
    command: str,
    directory: str | Path = DEFAULT_CAPTURE_DIR,
) -> Path:
    """Create a timestamped path for a laboratory capture."""

    capture_directory = Path(directory)
    capture_directory.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    safe_command = command.strip().replace(" ", "-").replace("/", "-")

    return capture_directory / (
        f"{timestamp}_lab_{safe_command}.log"
    )


class CaptureTransport:
    """Wrap a byte transport and record every transmitted and received byte."""

    def __init__(self, transport, capture):
        self.transport = transport
        self.capture = capture

    def record(self, direction: str, payload: bytes) -> None:
        payload = bytes(payload)
        timestamp = datetime.now().isoformat(timespec="milliseconds")

        self.capture.write(
            f"{timestamp} {direction} "
            f"{payload.hex(' ').upper()}\n"
        )
        self.capture.flush()

    def write(self, payload):
        payload = bytes(payload)
        self.record("TX", payload)
        return self.transport.write(payload)

    def read(self, size: int = 1):
        payload = self.transport.read(size)

        if payload:
            self.record("RX", payload)

        return payload

    def flush(self):
        flush = getattr(self.transport, "flush", None)

        if callable(flush):
            return flush()

        return None

    def close(self) -> None:
        close = getattr(self.transport, "close", None)

        if callable(close):
            close()


@contextmanager
def open_controller(
    command: str,
    port: str = DEFAULT_PORT,
    baud: int = DEFAULT_BAUD,
    timeout: float = DEFAULT_TIMEOUT,
    capture_dir: str | Path = DEFAULT_CAPTURE_DIR,
) -> Iterator[tuple[A125Controller, Path]]:
    """
    Open an exclusively owned A125 controller and capture its byte traffic.

    The serial connection and capture file are closed automatically.
    """

    require_exclusive_access()

    if not os.path.exists(port):
        raise FileNotFoundError(
            f"Serial device not found: {port}"
        )

    try:
        import serial
    except ImportError as error:
        raise RuntimeError(
            "PySerial is unavailable in this Python environment"
        ) from error

    path = build_capture_path(command, capture_dir)
    connection = None

    try:
        with path.open("w", encoding="utf-8") as capture:
            capture.write("TruePanel Project Stargate Laboratory\n")
            capture.write(f"Command: {command}\n")
            capture.write(f"Port: {port}\n")
            capture.write(f"Baud: {baud}\n")
            capture.write(f"Timeout: {timeout}\n\n")
            capture.flush()

            connection = serial.Serial(
                port,
                int(baud),
                timeout=float(timeout),
                write_timeout=float(timeout),
            )

            transport = CaptureTransport(connection, capture)
            controller = A125Controller(
                transport,
                timeout=float(timeout),
            )

            controller.stop_auto_display_reply()

            try:
                yield controller, path
            finally:
                try:
                    controller.clear()
                except Exception:
                    pass

                try:
                    controller.start_auto_display()
                except Exception:
                    pass
    finally:
        if connection is not None:
            try:
                connection.close()
            except Exception:
                pass
