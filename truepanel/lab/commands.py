"""
Project Stargate Laboratory.

Interactive, known-safe tooling for the QNAP A125 front panel.
Undocumented controller commands are intentionally excluded.
"""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import asdict, dataclass, field

from truepanel.lab.capture import (
    DEFAULT_BAUD,
    DEFAULT_CAPTURE_DIR,
    DEFAULT_PORT,
    DEFAULT_TIMEOUT,
    open_controller,
    service_is_active,
)
from truepanel.lab.experiments import (
    RepeatSample,
    run_repeat_experiment,
)


@dataclass
class LabResult:
    command: str
    success: bool
    value: str = ""
    detail: str = ""
    capture_path: str = ""
    data: dict[str, object] = field(default_factory=dict)



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



def print_repeat_sample(sample: RepeatSample) -> None:
    if sample.success:
        print(
            f"{sample.index:03d}: "
            f"value=0x{sample.value:04X} "
            f"latency={sample.latency_ms:.3f} ms"
        )
    else:
        print(
            f"{sample.index:03d}: "
            f"FAIL latency={sample.latency_ms:.3f} ms "
            f"{sample.error}"
        )


def run_repeat(args) -> LabResult:
    command_name = f"repeat-{args.query}"

    with open_controller(
        command_name,
        args.port,
        args.baud,
        args.timeout,
        args.capture_dir,
    ) as (controller, capture):
        result = run_repeat_experiment(
            controller=controller,
            query=args.query,
            count=args.count,
            interval=args.interval,
            sample_callback=(
                None
                if args.json_output
                else print_repeat_sample
            ),
        )

        latency = result.latency

        if latency.count:
            latency_detail = (
                f"min={latency.minimum_ms:.3f} ms, "
                f"avg={latency.average_ms:.3f} ms, "
                f"median={latency.median_ms:.3f} ms, "
                f"p95={latency.p95_ms:.3f} ms, "
                f"max={latency.maximum_ms:.3f} ms"
            )
        else:
            latency_detail = "No successful latency samples"

        consistency = (
            "consistent"
            if result.values_consistent
            else "variable"
        )

        return LabResult(
            command="repeat",
            success=result.failures == 0,
            value=(
                f"{result.successes}/{result.requested_count} "
                f"successful; values {consistency}"
            ),
            detail=latency_detail,
            capture_path=str(capture),
            data=result.as_dict(),
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

    repeat = commands.add_parser(
        "repeat",
        help="Repeat a safe query and measure latency",
    )
    repeat.add_argument(
        "--query",
        choices=("board", "version", "buttons"),
        default="board",
    )
    repeat.add_argument(
        "--count",
        type=int,
        default=25,
    )
    repeat.add_argument(
        "--interval",
        type=float,
        default=0.10,
        help="Seconds between queries",
    )
    repeat.set_defaults(handler=run_repeat)

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
