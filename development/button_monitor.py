#!/usr/bin/env python3
"""
TruePanel A125 Raw Button Monitor

Stops the controller's automatic display mode once, continuously polls the
button-status command, and prints every raw response frame. Automatic display
mode is restored when the monitor exits.

This is an experimental Project Stargate utility. Stop truepanel.service before
running it so the serial port has a single owner.
"""

from __future__ import annotations

import argparse
import signal
import sys
import time
from dataclasses import dataclass

import serial


PREAMBLE = 0x4D
RESPONSE_PREAMBLE = 0x53

CMD_BUTTONS = 0x06
CMD_STOP_AUTO_DISPLAY = 0x28
CMD_START_AUTO_DISPLAY = 0x29

NORMAL_RESPONSE = 0x05
ALTERNATE_RESPONSE = 0xFB


@dataclass(frozen=True)
class MonitorConfig:
    port: str
    baud: int
    interval: float
    timeout: float
    settle_time: float


class ButtonMonitor:
    def __init__(self, config: MonitorConfig) -> None:
        self.config = config
        self.running = True
        self.serial: serial.Serial | None = None
        self.last_normal_value: int | None = None
        self.last_alternate_code: int | None = None

    def request_stop(self, _signum: int, _frame: object) -> None:
        self.running = False

    def send_command(self, opcode: int) -> None:
        if self.serial is None:
            raise RuntimeError("Serial port is not open")

        self.serial.write(bytes((PREAMBLE, opcode)))
        self.serial.flush()

    def collect_response(self) -> bytes:
        if self.serial is None:
            raise RuntimeError("Serial port is not open")

        first = self.serial.read(1)
        if not first:
            return b""

        deadline = time.monotonic() + self.config.settle_time
        response = bytearray(first)

        while time.monotonic() < deadline:
            waiting = self.serial.in_waiting

            if waiting:
                response.extend(self.serial.read(waiting))
                deadline = time.monotonic() + self.config.settle_time
            else:
                time.sleep(0.002)

        return bytes(response)

    @staticmethod
    def format_hex(data: bytes) -> str:
        return " ".join(f"{byte:02X}" for byte in data)

    def describe_frame(self, frame: bytes) -> str:
        if not frame:
            return "TIMEOUT"

        if (
            len(frame) == 4
            and frame[0] == RESPONSE_PREAMBLE
            and frame[1] == NORMAL_RESPONSE
        ):
            value = int.from_bytes(frame[2:4], byteorder="big")
            changed = value != self.last_normal_value
            self.last_normal_value = value

            marker = "CHANGED" if changed else "same"
            return f"NORMAL value=0x{value:04X} {marker}"

        if (
            len(frame) == 3
            and frame[0] == RESPONSE_PREAMBLE
            and frame[1] == ALTERNATE_RESPONSE
        ):
            code = frame[2]
            changed = code != self.last_alternate_code
            self.last_alternate_code = code

            marker = "CHANGED" if changed else "same"
            return f"ALTERNATE code=0x{code:02X} {marker}"

        return f"UNKNOWN length={len(frame)}"

    def run(self) -> int:
        print("TruePanel Project Stargate")
        print("A125 Raw Button Monitor")
        print()
        print(f"Port:     {self.config.port}")
        print(f"Baud:     {self.config.baud}")
        print(f"Interval: {self.config.interval:.3f} seconds")
        print()
        print("Press LCD Up, LCD Down, and Copy one at a time.")
        print("Hold each button for roughly two seconds.")
        print("Press Ctrl+C when finished.")
        print()

        try:
            self.serial = serial.Serial(
                port=self.config.port,
                baudrate=self.config.baud,
                timeout=self.config.timeout,
                write_timeout=1.0,
            )

            self.serial.reset_input_buffer()
            self.serial.reset_output_buffer()

            self.send_command(CMD_STOP_AUTO_DISPLAY)
            time.sleep(0.050)
            self.serial.reset_input_buffer()

            sequence = 0

            while self.running:
                sequence += 1

                self.send_command(CMD_BUTTONS)
                frame = self.collect_response()

                timestamp = time.strftime("%H:%M:%S")
                milliseconds = int((time.time() % 1) * 1000)
                raw = self.format_hex(frame) if frame else "--"
                description = self.describe_frame(frame)

                print(
                    f"{timestamp}.{milliseconds:03d} "
                    f"#{sequence:05d} RX {raw:<20} {description}",
                    flush=True,
                )

                time.sleep(self.config.interval)

            return 0

        except serial.SerialException as exc:
            print(f"Serial error: {exc}", file=sys.stderr)
            return 1

        finally:
            if self.serial is not None and self.serial.is_open:
                try:
                    self.send_command(CMD_START_AUTO_DISPLAY)
                    time.sleep(0.050)
                except serial.SerialException:
                    pass

                self.serial.close()

            print()
            print("Automatic display mode restored.")
            print("Monitor stopped.")


def parse_args() -> MonitorConfig:
    parser = argparse.ArgumentParser(
        description="Continuously inspect raw A125 button responses."
    )
    parser.add_argument("--port", default="/dev/ttyS1")
    parser.add_argument("--baud", type=int, default=1200)
    parser.add_argument("--interval", type=float, default=0.100)
    parser.add_argument("--timeout", type=float, default=0.200)
    parser.add_argument("--settle-time", type=float, default=0.040)

    args = parser.parse_args()

    return MonitorConfig(
        port=args.port,
        baud=args.baud,
        interval=max(args.interval, 0.050),
        timeout=max(args.timeout, 0.050),
        settle_time=max(args.settle_time, 0.010),
    )


def main() -> int:
    monitor = ButtonMonitor(parse_args())

    signal.signal(signal.SIGINT, monitor.request_stop)
    signal.signal(signal.SIGTERM, monitor.request_stop)

    return monitor.run()


if __name__ == "__main__":
    raise SystemExit(main())
