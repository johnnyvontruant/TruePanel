"""Standalone one-command entry point for built-in HoloDeck missions."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from .missions import mission_names
from .report import run_mission_report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python3 -m truepanel.holodeck",
        description="Run deterministic TruePanel HoloDeck incident missions",
    )
    actions = parser.add_subparsers(dest="action", required=True)

    actions.add_parser("list", help="List built-in incident missions")

    run = actions.add_parser(
        "run",
        help="Run one mission and print its flight report",
    )
    run.add_argument("mission", choices=mission_names())
    run.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Print the complete machine-readable flight report",
    )
    run.add_argument(
        "--runtime-dir",
        type=Path,
        help="Use an explicit isolated runtime directory",
    )
    return parser


def _print_human(report: dict) -> None:
    status = "PASS" if report["invariants"]["passed"] else "FAIL"
    print(f"HoloDeck mission: {report['mission']}")
    print(f"Result: {status}")
    print(f"Simulated time: {report['simulated_seconds']:.1f}s")
    print(f"Scenario events: {report['scenario_event_count']}")
    print(f"Observations: {report['observation_count']}")
    print(f"Mission Control events: {report['mission_event_count']}")
    print(
        "Invariants: "
        f"{report['invariants']['rule_count']} rules, "
        f"{report['invariants']['violation_count']} violations"
    )
    final = report["final"]
    print(
        "Final state: "
        f"CPU {final['cpu_temperature_c']}C, "
        f"telemetry={'fresh' if final['telemetry_fresh'] else 'stale'}, "
        f"LCD={'connected' if final['lcd_connected'] else 'disconnected'}, "
        f"network={'up' if final['primary_network_up'] else 'down'}"
    )
    pools = ", ".join(
        f"{name}={health}"
        for name, health in sorted(final["pool_health"].items())
    )
    print(f"Pools: {pools}")


def _execute(args) -> int:
    if args.action == "list":
        for name in mission_names():
            print(name)
        return 0

    if args.runtime_dir is not None:
        report = run_mission_report(
            args.mission,
            runtime_dir=args.runtime_dir,
        )
    else:
        with TemporaryDirectory(prefix="truepanel-holodeck-mission-") as directory:
            report = run_mission_report(
                args.mission,
                runtime_dir=directory,
            )

    if args.json_output:
        print(json.dumps(report, sort_keys=True))
    else:
        _print_human(report)
    return 0 if report["invariants"]["passed"] else 1


def main(argv: list[str] | None = None) -> int:
    return _execute(build_parser().parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
