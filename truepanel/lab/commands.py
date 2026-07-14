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
from truepanel.lab.discovery import (
    DiscoveryProbeResult,
    run_discovery,
)
from truepanel.lab.experiments import (
    RepeatSample,
    run_repeat_experiment,
)
from truepanel.lab.planner import (
    build_plan_from_expression,
)
from truepanel.lab.execution import (
    ExecutionObservation,
)
from truepanel.lab.display_experiment import (
    build_characterization,
)
from truepanel.lab.display_runner import (
    DisplayExperimentRunner,
    FrameExecution,
)
from truepanel.lab.display_timing import (
    DisplayTimingSample,
    measure_clear,
    measure_frame_write,
    measure_line_write,
)
from truepanel.lab.interlock import (
    ARMING_PHRASE,
    build_execution_context,
    run_hardware_execution,
    run_simulated_execution,
)
from truepanel.lab.fingerprint import (
    ControllerFingerprint,
)
from truepanel.lab.capability_format import (
    capability_report_to_json,
    render_capability_report,
)
from truepanel.lab.fingerprint_format import (
    fingerprint_to_json,
    render_fingerprint,
)
from truepanel.lab.service import LaboratoryService


@dataclass
class LabResult:
    command: str
    success: bool
    value: str = ""
    detail: str = ""
    capture_path: str = ""
    data: dict[str, object] = field(default_factory=dict)



def run_capabilities(args) -> LabResult:
    """Build the baseline or live capability report."""

    service = LaboratoryService()

    if args.live:
        with open_controller(
            "capabilities",
            args.port,
            args.baud,
            args.timeout,
            args.capture_dir,
        ) as (controller, capture):
            report = service.detect_capabilities(controller)
            capture_path = str(capture)
            detail = "Live documented read-only capability detection"
    else:
        report = service.build_baseline_capability_report()
        capture_path = ""
        detail = "Recorded baseline capability knowledge"

    result = LabResult(
        command="capabilities",
        success=report.healthy,
        value=(
            f"{report.supported}/"
            f"{len(report.results)} supported"
        ),
        detail=detail,
        capture_path=capture_path,
        data=report.as_dict(),
    )

    result._capability_report = report

    return result


def _build_live_fingerprint(
    args,
) -> tuple[ControllerFingerprint, str]:
    """Acquire a fingerprint through capability providers."""

    with open_controller(
        "fingerprint",
        args.port,
        args.baud,
        args.timeout,
        args.capture_dir,
    ) as (controller, capture):
        fingerprint, capability_report = (
            LaboratoryService().build_live_fingerprint(
                controller,
                capture_path=str(capture),
            )
        )

        fingerprint.merge_metadata(
            {
                "capability_report": (
                    capability_report.as_dict()
                ),
            }
        )

        return fingerprint, str(capture)

def run_fingerprint(args) -> LabResult:
    """Build the baseline or live controller fingerprint."""

    if args.live:
        fingerprint, capture_path = _build_live_fingerprint(args)
        detail = "Live known-safe controller fingerprint"
    else:
        fingerprint = LaboratoryService().build_fingerprint()
        capture_path = ""
        detail = "Canonical Project Stargate controller profile"

    result = LabResult(
        command="fingerprint",
        success=True,
        value=fingerprint.controller_family,
        detail=detail,
        capture_path=capture_path,
        data=fingerprint.to_dict(),
    )

    # Keep the assembled object for rendering without probing twice.
    result._fingerprint = fingerprint

    return result


def print_display_timing_sample(
    sample: DisplayTimingSample,
) -> None:
    """Print one display timing sample."""

    if sample.success:
        print(
            f"{sample.index:03d}: "
            f"{sample.operation} "
            f"{sample.latency_ms:.3f} ms"
        )
    else:
        print(
            f"{sample.index:03d}: "
            f"{sample.operation} FAIL "
            f"{sample.latency_ms:.3f} ms "
            f"{sample.detail}"
        )


def run_display_timing(args) -> LabResult:
    """Measure host-side transmission latency for display commands."""

    if args.count < 1:
        raise ValueError("count must be at least 1")

    if args.interval < 0:
        raise ValueError("interval must be non-negative")

    callback = (
        None
        if args.json_output
        else print_display_timing_sample
    )

    with open_controller(
        f"timing-{args.timing_operation}",
        args.port,
        args.baud,
        args.timeout,
        args.capture_dir,
    ) as (controller, capture):
        if args.timing_operation == "clear":
            result = measure_clear(
                controller,
                count=args.count,
                interval=args.interval,
                callback=callback,
            )

        elif args.timing_operation == "row":
            result = measure_line_write(
                controller,
                row=args.row,
                text=args.text,
                count=args.count,
                interval=args.interval,
                callback=callback,
            )

        elif args.timing_operation == "frame":
            result = measure_frame_write(
                controller,
                line1=args.line1,
                line2=args.line2,
                count=args.count,
                interval=args.interval,
                callback=callback,
            )

        else:
            raise ValueError(
                f"unsupported timing operation: "
                f"{args.timing_operation}"
            )

        latency = result.latency

        detail = (
            f"min={latency.minimum_ms:.3f} ms, "
            f"avg={latency.average_ms:.3f} ms, "
            f"median={latency.median_ms:.3f} ms, "
            f"p95={latency.p95_ms:.3f} ms, "
            f"max={latency.maximum_ms:.3f} ms"
            if latency.count
            else "No successful timing samples"
        )

        return LabResult(
            command=f"timing-{args.timing_operation}",
            success=result.healthy,
            value=(
                f"{result.successes}/"
                f"{result.requested_count} successful"
            ),
            detail=detail,
            capture_path=str(capture),
            data=result.as_dict(),
        )


def print_display_frame(
    execution: FrameExecution,
) -> None:
    """Print progress for one display-experiment frame."""

    print()
    print(
        f"Frame {execution.index}/{execution.total}"
    )
    print(execution.frame.line1)
    print(execution.frame.line2)


def run_display_characterize(args) -> LabResult:
    """Run the documented display characterization sequence."""

    if args.duration < 0:
        raise ValueError(
            "frame duration must be non-negative"
        )

    experiment = build_characterization(
        duration_seconds=args.duration,
    )

    with open_controller(
        "display-characterize",
        args.port,
        args.baud,
        args.timeout,
        args.capture_dir,
    ) as (controller, capture):
        runner = DisplayExperimentRunner(controller)

        runner.run(
            experiment,
            callback=(
                None
                if args.json_output
                else print_display_frame
            ),
        )

        return LabResult(
            command="display-characterize",
            success=True,
            value=(
                f"{len(experiment.frames)} frames completed"
            ),
            detail=(
                "Documented clear/write display experiment"
            ),
            capture_path=str(capture),
            data={
                "experiment": experiment.name,
                "frame_count": len(experiment.frames),
                "duration_seconds": args.duration,
                "frames": [
                    {
                        "line1": frame.line1,
                        "line2": frame.line2,
                        "duration_seconds": (
                            frame.duration_seconds
                        ),
                    }
                    for frame in experiment.frames
                ],
            },
        )


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






def print_execution_observation(
    observation: ExecutionObservation,
) -> None:
    mode = "SIM" if observation.simulated else "HW"

    if observation.success:
        value = (
            f" value={observation.value_hex}"
            if observation.value_hex
            else ""
        )

        print(
            f"{mode} {observation.opcode_hex} PASS"
            f"{value} "
            f"latency={observation.latency_ms:.3f} ms"
        )
    else:
        print(
            f"{mode} {observation.opcode_hex} FAIL "
            f"latency={observation.latency_ms:.3f} ms "
            f"{observation.detail}"
        )


def run_survey(args) -> LabResult:
    plan = build_plan_from_expression(
        args.opcodes,
        allow_experimental_read_only=False,
        allow_experimental_stateful=False,
        allow_documented_writes=False,
    )

    simulation = not args.hardware

    context = build_execution_context(
        plan=plan,
        simulation=simulation,
        arming_phrase=args.arm,
        cooldown_seconds=args.cooldown,
        stop_on_failure=True,
    )

    callback = (
        None
        if args.json_output
        else print_execution_observation
    )

    if simulation:
        run_simulated_execution(
            context,
            callback=callback,
        )

        capture_path = ""
    else:
        with open_controller(
            "survey-read-only",
            args.port,
            args.baud,
            args.timeout,
            args.capture_dir,
        ) as (controller, capture):
            run_hardware_execution(
                context,
                controller,
                callback=callback,
            )

            capture_path = str(capture)

    return LabResult(
        command="survey",
        success=context.healthy,
        value=(
            f"{context.successes}/{plan.count} "
            f"probes successful"
        ),
        detail=(
            f"mode={'SIMULATION' if simulation else 'HARDWARE'}, "
            f"state={context.state.value}"
            + (
                f", abort={context.abort_reason}"
                if context.abort_reason
                else ""
            )
        ),
        capture_path=capture_path,
        data=context.as_dict(),
    )

def run_plan(args) -> LabResult:
    plan = build_plan_from_expression(
        args.opcodes,
        allow_experimental_read_only=(
            args.allow_experimental_read_only
        ),
        allow_experimental_stateful=(
            args.allow_experimental_stateful
        ),
        allow_documented_writes=(
            args.allow_documented_writes
        ),
    )

    categories = {}

    for entry in plan.entries:
        risk = entry.policy.risk.value
        categories[risk] = categories.get(risk, 0) + 1

    category_text = ", ".join(
        f"{name}={count}"
        for name, count in sorted(categories.items())
    )

    return LabResult(
        command="plan",
        success=True,
        value=f"{plan.count} opcodes validated",
        detail=category_text,
        data=plan.as_dict(),
    )

def print_discovery_probe(
    result: DiscoveryProbeResult,
) -> None:
    if result.success:
        print(
            f"{result.name:<10} "
            f"opcode=0x{result.opcode:02X} "
            f"value={result.value_hex} "
            f"latency={result.latency_ms:.3f} ms "
            f"[{result.response.response_name}]"
        )
    else:
        print(
            f"{result.name:<10} "
            f"opcode=0x{result.opcode:02X} "
            f"FAIL "
            f"latency={result.latency_ms:.3f} ms "
            f"[{result.response.classification.value}] "
            f"{result.response.detail}"
        )


def run_discover(args) -> LabResult:
    with open_controller(
        "discover",
        args.port,
        args.baud,
        args.timeout,
        args.capture_dir,
    ) as (controller, capture):
        report = run_discovery(
            controller,
            probe_callback=(
                None
                if args.json_output
                else print_discovery_probe
            ),
        )

        latency = report.latency

        if latency.count:
            latency_detail = (
                f"min={latency.minimum_ms:.3f} ms, "
                f"avg={latency.average_ms:.3f} ms, "
                f"median={latency.median_ms:.3f} ms, "
                f"max={latency.maximum_ms:.3f} ms"
            )
        else:
            latency_detail = "No successful latency samples"

        identity = []

        if report.board_id is not None:
            identity.append(
                f"board=0x{report.board_id:04X}"
            )

        if report.protocol_version is not None:
            identity.append(
                "protocol="
                f"0x{report.protocol_version:04X}"
            )

        return LabResult(
            command="discover",
            success=report.healthy,
            value=(
                f"{report.successes}/"
                f"{len(report.results)} probes successful"
                + (
                    "; " + ", ".join(identity)
                    if identity
                    else ""
                )
            ),
            detail=latency_detail,
            capture_path=str(capture),
            data=report.as_dict(),
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

    capabilities = commands.add_parser(
        "capabilities",
        help="Show detected controller capabilities",
    )
    capabilities.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        default=argparse.SUPPRESS,
        help="Emit the capability report as JSON",
    )
    capabilities.add_argument(
        "--compact",
        action="store_true",
        help="Emit compact JSON; implies --json",
    )
    capabilities.add_argument(
        "--live",
        action="store_true",
        help=(
            "Run documented read-only capability providers "
            "against the controller"
        ),
    )
    capabilities.set_defaults(handler=run_capabilities)

    fingerprint = commands.add_parser(
        "fingerprint",
        help="Show the current controller fingerprint",
    )
    fingerprint.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        default=argparse.SUPPRESS,
        help="Emit the fingerprint as JSON",
    )
    fingerprint.add_argument(
        "--compact",
        action="store_true",
        help="Emit compact JSON; implies --json",
    )
    fingerprint.add_argument(
        "--live",
        action="store_true",
        help=(
            "Acquire identity and timing through the "
            "known-safe discovery sequence"
        ),
    )
    fingerprint.set_defaults(handler=run_fingerprint)

    timing = commands.add_parser(
        "timing",
        help="Measure documented display command transmission timing",
    )
    timing_commands = timing.add_subparsers(
        dest="timing_operation",
        required=True,
    )

    timing_clear = timing_commands.add_parser(
        "clear",
        help="Measure display-clear transmission latency",
    )
    timing_clear.add_argument("--count", type=int, default=25)
    timing_clear.add_argument("--interval", type=float, default=0.05)
    timing_clear.set_defaults(handler=run_display_timing)

    timing_row = timing_commands.add_parser(
        "row",
        help="Measure one-row display-write transmission latency",
    )
    timing_row.add_argument("--row", type=int, choices=(0, 1), default=0)
    timing_row.add_argument(
        "--text",
        default="ABCDEFGHIJKLMNOP",
    )
    timing_row.add_argument("--count", type=int, default=25)
    timing_row.add_argument("--interval", type=float, default=0.05)
    timing_row.set_defaults(handler=run_display_timing)

    timing_frame = timing_commands.add_parser(
        "frame",
        help="Measure two-row frame transmission latency",
    )
    timing_frame.add_argument(
        "--line1",
        default="ABCDEFGHIJKLMNOP",
    )
    timing_frame.add_argument(
        "--line2",
        default="QRSTUVWXYZ012345",
    )
    timing_frame.add_argument("--count", type=int, default=25)
    timing_frame.add_argument("--interval", type=float, default=0.05)
    timing_frame.set_defaults(handler=run_display_timing)

    display = commands.add_parser(
        "display",
        help="Run documented display experiments",
    )
    display_commands = display.add_subparsers(
        dest="display_command",
        required=True,
    )

    characterize = display_commands.add_parser(
        "characterize",
        help="Run the standard display characterization",
    )
    characterize.add_argument(
        "--duration",
        type=float,
        default=1.0,
        help="Seconds to display each frame",
    )
    characterize.set_defaults(
        handler=run_display_characterize
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

    discover = commands.add_parser(
        "discover",
        help="Run safe controller discovery",
    )
    discover.set_defaults(handler=run_discover)

    plan = commands.add_parser(
        "plan",
        help="Validate an opcode survey without transmitting",
    )
    plan.add_argument(
        "--opcodes",
        required=True,
        help=(
            "Comma-separated opcodes and ranges, "
            "for example 0x00,0x06-0x08"
        ),
    )
    plan.add_argument(
        "--allow-experimental-read-only",
        action="store_true",
    )
    plan.add_argument(
        "--allow-experimental-stateful",
        action="store_true",
    )
    plan.add_argument(
        "--allow-documented-writes",
        action="store_true",
    )
    plan.set_defaults(handler=run_plan)

    survey = commands.add_parser(
        "survey",
        help="Run an interlocked read-only survey",
    )
    survey.add_argument(
        "--opcodes",
        required=True,
        help="Approved read-only opcodes to execute",
    )
    survey.add_argument(
        "--hardware",
        action="store_true",
        help="Use hardware instead of simulation",
    )
    survey.add_argument(
        "--arm",
        default="",
        help=(
            "Exact hardware arming phrase; required with "
            "--hardware"
        ),
    )
    survey.add_argument(
        "--cooldown",
        type=float,
        default=0.10,
        help="Seconds between probes",
    )
    survey.set_defaults(handler=run_survey)

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

    if result.data and result.command == "discover":
        board_id = result.data.get("board_id_hex")
        protocol = result.data.get("protocol_version_hex")
        buttons = result.data.get("button_status_hex")

        print()
        print("Discovery Identity")

        if board_id:
            print(f"  Board ID:         {board_id}")

        if protocol:
            print(f"  Protocol version: {protocol}")

        if buttons:
            print(f"  Button status:    {buttons}")

    if result.data and result.command == "plan":
        print()
        print("Survey Plan")

        for entry in result.data.get("entries", []):
            policy = entry["policy"]

            print(
                f"  {entry['opcode_hex']} "
                f"{policy['risk']}: "
                f"{policy['reason']}"
            )

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

    if result.command == "capabilities" and result.success:
        report = getattr(result, "_capability_report", None)

        if report is None:
            raise RuntimeError(
                "capabilities command returned no capability report"
            )

        if args.json_output or getattr(args, "compact", False):
            print(
                capability_report_to_json(
                    report,
                    indent=(
                        None
                        if getattr(args, "compact", False)
                        else 2
                    ),
                )
            )
        else:
            print(render_capability_report(report))
    elif result.command == "fingerprint" and result.success:
        fingerprint = getattr(result, "_fingerprint", None)

        if fingerprint is None:
            raise RuntimeError(
                "fingerprint command returned no fingerprint object"
            )

        if args.json_output or getattr(args, "compact", False):
            print(
                fingerprint_to_json(
                    fingerprint,
                    indent=(
                        None
                        if getattr(args, "compact", False)
                        else 2
                    ),
                )
            )
        else:
            print(render_fingerprint(fingerprint))
    elif args.json_output:
        print(json.dumps(asdict(result), indent=2))
    else:
        print_result(result)

    return 0 if result.success else 1


if __name__ == "__main__":
    raise SystemExit(main())
