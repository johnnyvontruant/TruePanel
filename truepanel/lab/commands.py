"""
Project Stargate Laboratory.

Interactive, known-safe tooling for the QNAP A125 front panel.
Undocumented controller commands are intentionally excluded.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

from truepanel.hardware.a125 import A125Controller


DEFAULT_PORT = "/dev/ttyS1"
DEFAULT_BAUD = 1200
DEFAULT_TIMEOUT = 1.0
DEFAULT_CAPTURE_DIR = Path("development/logs")


@dataclass
class LabResult:
    command: str
    success: bool
    value: str = ""
    detail: str = ""
    capture_path: str = ""


def service_is_active(service="truepanel") -> bool:
    result = subprocess.run(
        ["systemctl", "is-active", "--quiet", service],
        check=False,
    )
    return result.returncode == 0


def require_exclusive_access() -> None:
    if service_is_active():
        raise RuntimeError(
            "truepanel.service is running. Run:\n"
            "  systemctl stop truepanel\n"
            "before using the Stargate Laboratory."
        )


def capture_path(command, directory=DEFAULT_CAPTURE_DIR) -> Path:
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_command = command.replace(" ", "-")

    return directory / f"{timestamp}_lab_{safe_command}.log"


class CaptureTransport:
    def __init__(self, transport, capture):
        self.transport = transport
        self.capture = capture

    def record(self, direction, payload):
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

    def read(self, size=1):
        payload = self.transport.read(size)

        if payload:
            self.record("RX", payload)

        return payload

    def flush(self):
        flush = getattr(self.transport, "flush", None)

        if callable(flush):
            flush()

    def close(self):
        close = getattr(self.transport, "close", None)

        if callable(close):
            close()


@contextmanager
def open_controller(
    command,
    port=DEFAULT_PORT,
    baud=DEFAULT_BAUD,
    timeout=DEFAULT_TIMEOUT,
    capture_dir=DEFAULT_CAPTURE_DIR,
):
    require_exclusive_access()

    if not os.path.exists(port):
        raise FileNotFoundError(f"Serial device not found: {port}")

    try:
        import serial
    except ImportError as error:
        raise RuntimeError(
            "PySerial is unavailable in this Python environment"
        ) from error

    path = capture_path(command, capture_dir)

    connection = None

    try:
        with path.open("w", encoding="utf-8") as capture:
            capture.write("TruePanel Project Stargate Laboratory\n")
            capture.write(f"Command: {command}\n")
            capture.write(f"Port: {port}\n")
            capture.write(f"Baud: {baud}\n\n")
            capture.flush()

            connection = serial.Serial(
                port,
                baud,
                timeout=timeout,
                write_timeout=timeout,
            )

            transport = CaptureTransport(connection, capture)
            controller = A125Controller(
                transport,
                timeout=timeout,
            )

            yield controller, path
    finally:
        if connection is not None:
            try:
                connection.close()
            except Exception:
                pass


def run_status(args) -> LabResult:
    active = service_is_active()

    return LabResult(
        command="status",
        success=True,
        value="LOCKED" if active else "READY",
        detail=(
            "truepanel.service owns the serial port"
            if active
            else "Serial port available for laboratory use"
        ),
    )


def run_board(args) -> LabResult:
    with open_controller(
        "board",
        args.port,
        args.baud,
        args.timeout,
        args.capture_dir,
    ) as (controller, capture):
        value = controller.query_board_id()

        return LabResult(
            command="board",
            success=True,
            value=f"0x{value:04X}",
            capture_path=str(capture),
        )


def run_version(args) -> LabResult:
    with open_controller(
        "version",
        args.port,
        args.baud,
        args.timeout,
        args.capture_dir,
    ) as (controller, capture):
        value = controller.query_protocol_version()

        return LabResult(
            command="version",
            success=True,
            value=f"0x{value:04X}",
            capture_path=str(capture),
        )


def run_buttons(args) -> LabResult:
    with open_controller(
        "buttons",
        args.port,
        args.baud,
        args.timeout,
        args.capture_dir,
    ) as (controller, capture):
        value = controller.query_buttons()

        return LabResult(
            command="buttons",
            success=True,
            value=f"0x{value:04X}",
            capture_path=str(capture),
        )


def run_clear(args) -> LabResult:
    with open_controller(
        "clear",
        args.port,
        args.baud,
        args.timeout,
        args.capture_dir,
    ) as (controller, capture):
        controller.clear()

        return LabResult(
            command="clear",
            success=True,
            value="Display cleared",
            capture_path=str(capture),
        )


def run_backlight(args) -> LabResult:
    enabled = args.state == "on"

    with open_controller(
        f"backlight-{args.state}",
        args.port,
        args.baud,
        args.timeout,
        args.capture_dir,
    ) as (controller, capture):
        controller.backlight(enabled)

        return LabResult(
            command="backlight",
            success=True,
            value=args.state.upper(),
            capture_path=str(capture),
        )


def run_write(args) -> LabResult:
    line1 = args.line1[:16]
    line2 = args.line2[:16]

    with open_controller(
        "write",
        args.port,
        args.baud,
        args.timeout,
        args.capture_dir,
    ) as (controller, capture):
        controller.write_frame(line1, line2)

        return LabResult(
            command="write",
            success=True,
            value=f"{line1!r} / {line2!r}",
            capture_path=str(capture),
        )


def run_monitor(args) -> LabResult:
    samples = max(1, args.samples)
    delay = max(0.05, args.delay)
    values = []

    with open_controller(
        "monitor",
        args.port,
        args.baud,
        args.timeout,
        args.capture_dir,
    ) as (controller, capture):
        for index in range(samples):
            value = controller.query_buttons()
            values.append(value)

            print(
                f"{index + 1:03d}: "
                f"buttons=0x{value:04X}"
            )

            if index + 1 < samples:
                time.sleep(delay)

        return LabResult(
            command="monitor",
            success=True,
            value=f"{len(values)} samples",
            capture_path=str(capture),
        )


def add_common_arguments(parser):
    parser.add_argument("--port", default=DEFAULT_PORT)
    parser.add_argument("--baud", type=int, default=DEFAULT_BAUD)
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT,
    )
    parser.add_argument(
        "--capture-dir",
        default=str(DEFAULT_CAPTURE_DIR),
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
    )


def build_parser():
    parser = argparse.ArgumentParser(
        description="Project Stargate A125 Laboratory"
    )

    add_common_arguments(parser)

    commands = parser.add_subparsers(
        dest="lab_command",
        required=True,
    )

    status = commands.add_parser("status")
    status.set_defaults(handler=run_status)

    board = commands.add_parser("board")
    board.set_defaults(handler=run_board)

    version = commands.add_parser("version")
    version.set_defaults(handler=run_version)

    buttons = commands.add_parser("buttons")
    buttons.set_defaults(handler=run_buttons)

    clear = commands.add_parser("clear")
    clear.set_defaults(handler=run_clear)

    backlight = commands.add_parser("backlight")
    backlight.add_argument(
        "state",
        choices=("on", "off"),
    )
    backlight.set_defaults(handler=run_backlight)

    write = commands.add_parser("write")
    write.add_argument("line1")
    write.add_argument("line2", nargs="?", default="")
    write.set_defaults(handler=run_write)

    monitor = commands.add_parser("monitor")
    monitor.add_argument("--samples", type=int, default=20)
    monitor.add_argument("--delay", type=float, default=0.25)
    monitor.set_defaults(handler=run_monitor)

    return parser


def print_result(result: LabResult) -> None:
    print()
    print("=" * 48)
    print("       TruePanel Project Stargate")
    print("             Laboratory")
    print("=" * 48)
    print(f"Command: {result.command}")
    print(f"Status: {'PASS' if result.success else 'FAIL'}")

    if result.value:
        print(f"Value: {result.value}")

    if result.detail:
        print(f"Detail: {result.detail}")

    if result.capture_path:
        print(f"Capture: {result.capture_path}")

    print("=" * 48)


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        result = args.handler(args)
    except Exception as error:
        result = LabResult(
            command=args.lab_command,
            success=False,
            detail=str(error),
        )

    if args.json_output:
        print(json.dumps(asdict(result), indent=2))
    else:
        print_result(result)

    return 0 if result.success else 1


if __name__ == "__main__":
    raise SystemExit(main())
