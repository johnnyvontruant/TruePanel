"""Command-line entry points for the TruePanel Digital Twin."""

from __future__ import annotations

import json
import math
from argparse import ArgumentTypeError, _SubParsersAction
from pathlib import Path
from tempfile import TemporaryDirectory

from truepanel.history.black_box import (
    MAX_BLACK_BOX_REPLAY_FRAMES,
    BlackBoxReplay,
)

from .catalog import HOSTS, host_fixture
from .clock import DeterministicClock
from .invariants import DEFAULT_INVARIANT_RULES, evaluate_timeline
from .provider import HoloDeckHostProvider
from .scenario import load_scenario

MAX_REPORT_STEPS = 1_000
MAX_COMPILER_EVALUATIONS = 1_000


def _bounded_integer(value: str, *, maximum: int, label: str) -> int:
    parsed = int(value)
    if not 1 <= parsed <= maximum:
        raise ArgumentTypeError(
            f"{label} must be between 1 and {maximum}"
        )
    return parsed


def _finite_nonnegative(
    value: str,
    *,
    label: str,
) -> float:
    parsed = float(value)

    if (
        not math.isfinite(parsed)
        or parsed < 0
    ):
        raise ArgumentTypeError(
            f"{label} must be finite and nonnegative"
        )

    return parsed


def add_holodeck_subcommands(subcommands: _SubParsersAction) -> None:
    parser = subcommands.add_parser(
        "holodeck",
        help="Run the hardware-isolated TruePanel Digital Twin",
    )
    actions = parser.add_subparsers(dest="holodeck_action", required=True)

    run = actions.add_parser("run", help="Replay a simulated host scenario")
    run.add_argument("host", choices=sorted(HOSTS), nargs="?", default="battlestation")
    run.add_argument("--scenario", type=Path, dest="holodeck_scenario")
    run.add_argument(
        "--steps",
        type=lambda value: _bounded_integer(
            value,
            maximum=MAX_REPORT_STEPS,
            label="steps",
        ),
        default=1,
    )
    run.add_argument(
        "--step-seconds",
        type=lambda value: _finite_nonnegative(
            value,
            label="step-seconds",
        ),
        default=10.0,
    )
    run.add_argument("--json", action="store_true", dest="holodeck_json")

    inject = actions.add_parser("inject", help="Apply one fault to a fresh twin")
    inject.add_argument("event_type")
    inject.add_argument("assignments", nargs="*", metavar="KEY=VALUE")
    inject.add_argument("--host", choices=sorted(HOSTS), default="battlestation")

    replay = actions.add_parser(
        "replay",
        help="Replay a privacy-safe Black Box recording through Mission Control",
    )
    replay.add_argument("recording", type=Path)
    replay.add_argument("--host", choices=sorted(HOSTS), default="battlestation")
    replay.add_argument("--json", action="store_true", dest="holodeck_json")

    check = actions.add_parser(
        "check",
        help="Evaluate bounded safety invariants against a scenario",
    )
    check.add_argument(
        "host",
        choices=sorted(HOSTS),
        nargs="?",
        default="battlestation",
    )
    check.add_argument("--scenario", type=Path, dest="holodeck_scenario")
    check.add_argument(
        "--steps",
        type=lambda value: _bounded_integer(
            value, maximum=MAX_REPORT_STEPS, label="steps"
        ),
        default=1,
    )
    check.add_argument(
        "--step-seconds",
        type=lambda value: _finite_nonnegative(
            value,
            label="step-seconds",
        ),
        default=10.0,
    )
    check.add_argument("--json", action="store_true", dest="holodeck_json")

    compile_incident = actions.add_parser(
        "compile-incident",
        help="Minimize one recorded invariant failure into regression data",
    )
    compile_incident.add_argument("recording", type=Path)
    compile_incident.add_argument(
        "--invariant",
        required=True,
        choices=sorted(rule.rule_id for rule in DEFAULT_INVARIANT_RULES),
    )
    compile_incident.add_argument(
        "--host",
        choices=sorted(HOSTS),
        default="battlestation",
    )
    compile_incident.add_argument("--name", default="black-box-incident")
    compile_incident.add_argument("--output", required=True, type=Path)
    compile_incident.add_argument(
        "--max-frames",
        type=lambda value: _bounded_integer(
            value,
            maximum=MAX_BLACK_BOX_REPLAY_FRAMES,
            label="max-frames",
        ),
        default=MAX_BLACK_BOX_REPLAY_FRAMES,
    )
    compile_incident.add_argument(
        "--max-evaluations",
        type=lambda value: _bounded_integer(
            value,
            maximum=MAX_COMPILER_EVALUATIONS,
            label="max-evaluations",
        ),
        default=MAX_COMPILER_EVALUATIONS,
    )


def _coerce(value: str):
    lowered = value.lower()
    if lowered in {"true", "false"}:
        return lowered == "true"
    try:
        return int(value)
    except ValueError:
        try:
            return float(value)
        except ValueError:
            return value


def _assignments(values: list[str]) -> dict:
    result = {}
    for assignment in values:
        if "=" not in assignment:
            raise ValueError(f"expected KEY=VALUE, got {assignment!r}")
        key, value = assignment.split("=", 1)
        result[key] = _coerce(value)
    return result


def _provider(args) -> HoloDeckHostProvider:
    scenario_path = getattr(args, "holodeck_scenario", None)
    scenario = load_scenario(scenario_path) if scenario_path else None
    if scenario is not None and scenario.host != args.host:
        raise ValueError(
            f"scenario requires host {scenario.host!r}, not {args.host!r}"
        )
    return HoloDeckHostProvider(
        host_fixture(args.host),
        scenario=scenario,
        clock=DeterministicClock(),
    )


def handle_holodeck_command(args) -> int | None:
    if getattr(args, "command", None) != "holodeck":
        return None

    if args.holodeck_action == "compile-incident":
        return _compile_incident(args)

    if args.holodeck_action == "replay":
        from .replay import BlackBoxHoloDeckProvider

        provider = BlackBoxHoloDeckProvider.from_recording(
            args.recording,
            host=args.host,
        )
    else:
        provider = _provider(args)

    if args.holodeck_action == "check":
        return _check_invariants(args, provider)

    if args.holodeck_action == "inject":
        state = provider.inject(args.event_type, **_assignments(args.assignments))
        print(json.dumps(state, indent=2, sort_keys=True))
        return 0

    with TemporaryDirectory(prefix="truepanel-holodeck-") as directory:
        from truepanel.web.snapshot import SnapshotService

        root = Path(directory)
        service = SnapshotService(
            collector=provider,
            config={"holodeck": {"simulation": True}},
            history_path=root / "history.jsonl",
            fan_control_status_path=root / "fan-status.json",
            lcd_reader_status_path=root / "lcd-reader.json",
            lcd_display_status_path=root / "lcd-display.json",
            fan_control_history_path=root / "fan-history.jsonl",
            thermal_observer_history_path=root / "thermal-history.jsonl",
            thermal_commissioning_history_path=root / "commissioning.jsonl",
            fan_status_provider=lambda: provider.update()["fans"],
            clock=provider.clock,
        )
        if args.holodeck_action == "replay":
            steps = len(provider.replay)
        else:
            steps = max(1, args.steps)
        for index in range(steps):
            if index:
                if args.holodeck_action == "replay":
                    provider.step()
                else:
                    provider.advance(args.step_seconds)
            payload = service.status()
            if args.holodeck_json:
                print(json.dumps(payload, sort_keys=True))
            else:
                print(
                    f"HoloDeck {args.host} t={provider.clock():.1f}s "
                    f"health={payload.get('health', {}).get('state', 'unknown')}"
                )
    return 0


def _invariant_payload(result) -> dict:
    """Return a compact, deterministic report without raw host state."""

    return {
        "passed": result.passed,
        "observation_count": result.observation_count,
        "rule_count": result.rule_count,
        "violation_count": len(result.violations),
        "violations": [
            {
                "rule_id": item.rule_id,
                "description": item.description,
                "observation_index": item.observation_index,
                "evidence": dict(item.evidence),
            }
            for item in result.violations
        ],
    }


def _check_invariants(args, provider) -> int:
    from .runner import HoloDeckScenarioRunner

    with TemporaryDirectory(prefix="truepanel-holodeck-check-") as directory:
        runner = HoloDeckScenarioRunner(provider, runtime_dir=directory)
        observations = []
        for index in range(args.steps):
            observations.append(
                runner.step(0 if index == 0 else args.step_seconds)
            )
    report = _invariant_payload(evaluate_timeline(observations))
    if args.holodeck_json:
        print(json.dumps(report, sort_keys=True))
    else:
        state = "PASS" if report["passed"] else "FAIL"
        print(
            f"HoloDeck invariants: {state} "
            f"({report['observation_count']} observations, "
            f"{report['rule_count']} rules, "
            f"{report['violation_count']} violations)"
        )
        for violation in report["violations"]:
            print(
                f"- {violation['rule_id']} at observation "
                f"{violation['observation_index']}"
            )
    return 0 if report["passed"] else 1


def _compile_incident(args) -> int:
    from .compiler import IncidentCompiler
    from .replay import BlackBoxHoloDeckProvider
    from .runner import HoloDeckScenarioRunner

    if args.output.exists():
        raise ValueError(f"refusing to overwrite existing output: {args.output}")

    selected = next(
        rule for rule in DEFAULT_INVARIANT_RULES if rule.rule_id == args.invariant
    )

    def violates(frames) -> bool:
        provider = BlackBoxHoloDeckProvider(
            BlackBoxReplay(frames),
            host=args.host,
        )
        with TemporaryDirectory(prefix="truepanel-holodeck-compile-") as directory:
            runner = HoloDeckScenarioRunner(provider, runtime_dir=directory)
            observations = []
            for index in range(len(frames)):
                if index:
                    provider.step()
                observations.append(runner.step())
        return not evaluate_timeline(observations, (selected,)).passed

    compiled = IncidentCompiler(
        violates,
        invariant_id=selected.rule_id,
        max_frames=args.max_frames,
        max_evaluations=args.max_evaluations,
    ).compile(
        args.recording,
        name=args.name,
        host=args.host,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(compiled.as_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(compiled.manifest, sort_keys=True))
    return 0


__all__ = ["add_holodeck_subcommands", "handle_holodeck_command"]
