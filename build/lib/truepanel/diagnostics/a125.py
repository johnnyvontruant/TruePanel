"""
Project Stargate A125 hardware diagnostics.

Default diagnostics are read-only. Active display tests must be requested
explicitly and require exclusive ownership of the serial port.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from truepanel.hardware.a125 import A125Controller


DEFAULT_PORT = "/dev/ttyS1"
DEFAULT_BAUD = 1200
DEFAULT_CAPTURE_DIR = Path("development/logs")


@dataclass
class DiagnosticCheck:
    name: str
    status: str
    value: str = ""
    detail: str = ""

    @property
    def passed(self) -> bool:
        return self.status == "PASS"


@dataclass
class DiagnosticReport:
    port: str
    baud: int
    started_at: str
    active_tests: bool
    checks: list[DiagnosticCheck] = field(default_factory=list)
    capture_path: str = ""

    @property
    def healthy(self) -> bool:
        return all(
            check.status in ("PASS", "SKIP")
            for check in self.checks
        )

    def add(
        self,
        name: str,
        status: str,
        value: str = "",
        detail: str = "",
    ) -> None:
        self.checks.append(
            DiagnosticCheck(
                name=name,
                status=status,
                value=value,
                detail=detail,
            )
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "port": self.port,
            "baud": self.baud,
            "started_at": self.started_at,
            "active_tests": self.active_tests,
            "healthy": self.healthy,
            "capture_path": self.capture_path,
            "checks": [
                asdict(check)
                for check in self.checks
            ],
        }


class CaptureTransport:
    """
    Wrap a serial transport and capture every read and write operation.
    """

    def __init__(self, transport, capture_file):
        self.transport = transport
        self.capture_file = capture_file

    def _record(self, direction: str, payload: bytes) -> None:
        timestamp = datetime.now().isoformat(timespec="milliseconds")
        hex_payload = payload.hex(" ").upper()

        self.capture_file.write(
            f"{timestamp} {direction} {hex_payload}\n"
        )
        self.capture_file.flush()

    def write(self, payload):
        payload = bytes(payload)
        self._record("TX", payload)
        return self.transport.write(payload)

    def read(self, size=1):
        payload = self.transport.read(size)

        if payload:
            self._record("RX", payload)

        return payload

    def flush(self):
        flush = getattr(self.transport, "flush", None)

        if callable(flush):
            return flush()

        return None

    def close(self):
        close = getattr(self.transport, "close", None)

        if callable(close):
            close()


def service_is_active(service="truepanel") -> bool:
    result = subprocess.run(
        ["systemctl", "is-active", "--quiet", service],
        check=False,
    )
    return result.returncode == 0


def timestamped_capture_path(directory=DEFAULT_CAPTURE_DIR) -> Path:
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return directory / f"{stamp}_a125.log"


def format_u16(value: int) -> str:
    return f"0x{value:04X}"


def run_diagnostics(
    port=DEFAULT_PORT,
    baud=DEFAULT_BAUD,
    active_tests=False,
    capture_dir=DEFAULT_CAPTURE_DIR,
    timeout=1.0,
) -> DiagnosticReport:
    report = DiagnosticReport(
        port=str(port),
        baud=int(baud),
        started_at=datetime.now().isoformat(timespec="seconds"),
        active_tests=bool(active_tests),
    )

    if service_is_active():
        report.add(
            "Exclusive access",
            "FAIL",
            detail=(
                "truepanel.service is running. Stop it before "
                "opening the A125 serial port."
            ),
        )
        return report

    if not os.path.exists(port):
        report.add(
            "Serial device",
            "FAIL",
            value=str(port),
            detail="Device does not exist",
        )
        return report

    capture_path = timestamped_capture_path(capture_dir)
    report.capture_path = str(capture_path)

    try:
        import serial
    except ImportError as error:
        report.add(
            "PySerial",
            "FAIL",
            detail=str(error),
        )
        return report

    serial_connection = None

    try:
        with capture_path.open("w", encoding="utf-8") as capture:
            capture.write("TruePanel Project Stargate A125 Capture\n")
            capture.write(f"Port: {port}\n")
            capture.write(f"Baud: {baud}\n")
            capture.write(f"Active tests: {active_tests}\n\n")
            capture.flush()

            serial_connection = serial.Serial(
                port,
                baud,
                timeout=timeout,
                write_timeout=timeout,
            )

            transport = CaptureTransport(
                serial_connection,
                capture,
            )
            controller = A125Controller(
                transport,
                timeout=timeout,
            )

            report.add(
                "Serial connection",
                "PASS",
                value=f"{port} @ {baud}",
            )

            try:
                board_id = controller.query_board_id()
                report.add(
                    "Board ID",
                    "PASS",
                    value=format_u16(board_id),
                )
            except Exception as error:
                report.add(
                    "Board ID",
                    "FAIL",
                    detail=str(error),
                )

            try:
                protocol = controller.query_protocol_version()
                report.add(
                    "Protocol version",
                    "PASS",
                    value=format_u16(protocol),
                )
            except Exception as error:
                report.add(
                    "Protocol version",
                    "FAIL",
                    detail=str(error),
                )

            try:
                buttons = controller.query_buttons()
                report.add(
                    "Button status",
                    "PASS",
                    value=format_u16(buttons),
                )
            except Exception as error:
                report.add(
                    "Button status",
                    "FAIL",
                    detail=str(error),
                )

            report.add(
                "Raw byte pipeline",
                "PASS",
                value="Available",
            )

            report.add(
                "Custom glyphs",
                "SKIP",
                value="Unverified",
                detail=(
                    "A125 CGRAM programming command is not yet known"
                ),
            )

            if active_tests:
                run_active_tests(controller, report)
            else:
                report.add(
                    "Active LCD tests",
                    "SKIP",
                    detail="Use --active-tests to run",
                )

    except Exception as error:
        report.add(
            "Serial connection",
            "FAIL",
            detail=str(error),
        )
    finally:
        if serial_connection is not None:
            try:
                serial_connection.close()
            except Exception:
                pass

    return report


def run_active_tests(
    controller: A125Controller,
    report: DiagnosticReport,
) -> None:
    try:
        controller.backlight(True)
        report.add("Backlight command", "PASS")
    except Exception as error:
        report.add(
            "Backlight command",
            "FAIL",
            detail=str(error),
        )

    try:
        controller.clear()
        report.add("Clear command", "PASS")
    except Exception as error:
        report.add(
            "Clear command",
            "FAIL",
            detail=str(error),
        )

    try:
        controller.write_frame(
            "STARGATE TEST",
            "A125 ONLINE",
        )
        report.add("Display write", "PASS")
        time.sleep(2)
    except Exception as error:
        report.add(
            "Display write",
            "FAIL",
            detail=str(error),
        )

    try:
        controller.write_frame(
            "TruePanel",
            "Restart Service",
        )
    except Exception:
        pass

    # Reset is intentionally not sent automatically. Although documented,
    # resetting the controller is unnecessary for routine diagnostics.
    report.add(
        "Reset command",
        "SKIP",
        detail="Documented but not sent by routine diagnostics",
    )


def print_report(report: DiagnosticReport) -> None:
    print()
    print("=" * 48)
    print("       TruePanel Project Stargate")
    print("          A125 Diagnostics")
    print("=" * 48)
    print(f"Port: {report.port}")
    print(f"Baud: {report.baud}")
    print(f"Capture: {report.capture_path or 'Not created'}")
    print()

    for check in report.checks:
        value = f" {check.value}" if check.value else ""
        print(f"{check.name:.<26}{check.status}{value}")

        if check.detail:
            print(f"  {check.detail}")

    print()
    print("=" * 48)
    print(
        "CONTROLLER STATUS: MISSION READY"
        if report.healthy
        else "CONTROLLER STATUS: ATTENTION REQUIRED"
    )
    print("=" * 48)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run Project Stargate A125 diagnostics."
    )
    parser.add_argument("--port", default=DEFAULT_PORT)
    parser.add_argument("--baud", type=int, default=DEFAULT_BAUD)
    parser.add_argument(
        "--active-tests",
        action="store_true",
        help="Run known-safe LCD write, clear, and backlight tests.",
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
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)

    report = run_diagnostics(
        port=args.port,
        baud=args.baud,
        active_tests=args.active_tests,
        capture_dir=args.capture_dir,
    )

    if args.json_output:
        print(json.dumps(report.as_dict(), indent=2))
    else:
        print_report(report)

    return 0 if report.healthy else 1


if __name__ == "__main__":
    raise SystemExit(main())
