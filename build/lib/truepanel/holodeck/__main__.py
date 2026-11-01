"""Standalone one-command entry point for built-in HoloDeck missions."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from .missions import mission_names
from .report import run_flight_deck_report, run_mission_report


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

    suite = actions.add_parser(
        "flight-deck",
        help="Run every built-in mission as one readiness exercise",
    )
    suite.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Print the machine-readable Flight Deck summary",
    )
    suite.add_argument(
        "--runtime-dir",
        type=Path,
        help="Use an explicit isolated runtime directory",
    )
    return parser


def _print_human(report: dict) -> None:
    status = "PASS" if report["passed"] else "FAIL"
    print(f"HoloDeck mission: {report['mission']}")
    print(f"Result: {status}")
    print(f"Simulated time: {report['simulated_seconds']:.1f}s")
    print(f"Scenario events: {report['scenario_event_count']}")
    print(f"Observations: {report['observation_count']}")
    print(f"Mission Control events: {report['mission_event_count']}")
    print(
        "Contracts: "
        f"{'PASS' if report['contracts']['passed'] else 'FAIL'} "
        f"({report['contracts']['check_count']} checks)"
    )
    acceptance = report["mission_control_acceptance"]
    print(
        "Mission Control acceptance: "
        f"{'PASS' if acceptance['passed'] else 'FAIL'} "
        f"({acceptance['check_count']} checks, "
        f"{acceptance['failed_count']} failed)"
    )
    temporal = report["temporal_semantics"]
    print(
        "Temporal semantics: "
        f"{'PASS' if temporal['passed'] else 'FAIL'} "
        f"({temporal['check_count']} checks, "
        f"{temporal['failed_count']} failed)"
    )
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


def _print_flight_deck(report: dict) -> None:
    status = "PASS" if report["passed"] else "FAIL"
    print(f"HoloDeck Flight Deck: {status}")
    print(
        f"Missions: {report['passed_count']}/{report['mission_count']} passed, "
        f"{report['failed_count']} failed"
    )
    print(
        "Mission Control acceptance: "
        f"{report['mission_control_acceptance_passed']}/"
        f"{report['mission_count']} passed"
    )
    print(
        "Temporal semantics: "
        f"{report['temporal_semantics_passed']}/"
        f"{report['mission_count']} passed"
    )
    print(f"Simulated time: {report['simulated_seconds']:.1f}s")
    print(f"Scenario events: {report['scenario_event_count']}")
    print(f"Mission Control events: {report['mission_event_count']}")
    for mission in report["missions"]:
        print(
            f"- {'PASS' if mission['passed'] else 'FAIL'} "
            f"{mission['mission']} "
            f"contracts={'PASS' if mission['contracts_passed'] else 'FAIL'} "
            "mission-control="
            f"{'PASS' if mission['mission_control_acceptance_passed'] else 'FAIL'} "
            f"temporal={'PASS' if mission['temporal_semantics_passed'] else 'FAIL'} "
            f"invariants={'PASS' if mission['invariants_passed'] else 'FAIL'}"
        )


def _runtime_report(args):
    if args.action == "flight-deck":
        return run_flight_deck_report(runtime_dir=args.runtime_dir)
    return run_mission_report(args.mission, runtime_dir=args.runtime_dir)


def _execute(args) -> int:
    if args.action == "list":
        for name in mission_names():
            print(name)
        return 0

    if args.runtime_dir is not None:
        report = _runtime_report(args)
    else:
        with TemporaryDirectory(prefix="truepanel-holodeck-mission-") as directory:
            args.runtime_dir = Path(directory)
            report = _runtime_report(args)

    if args.json_output:
        print(json.dumps(report, sort_keys=True))
    elif args.action == "flight-deck":
        _print_flight_deck(report)
    else:
        _print_human(report)
    return 0 if report["passed"] else 1


def main(argv: list[str] | None = None) -> int:
    return _execute(build_parser().parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
