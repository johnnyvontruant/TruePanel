"""
TruePanel CLI
"""

import argparse
import runpy
import time

from truepanel.collectors import create_collector
from truepanel.doctor import run_doctor
from truepanel.plugins import load_plugins


SCENARIOS = [
    "normal",
    "thermal",
    "pool",
    "smart",
    "resilver",
    "network",
    "capacity",
    "quiet-night",
    "everything",
]


def print_state(state):
    print("\nTruePanel Simulator")
    print("-------------------")
    print(f"Host: {state.get('hostname', 'unknown')}")
    print(f"CPU: {state.get('cpu_percent', 0)}%")
    print(f"RAM: {state.get('ram_percent', 0)}%")
    print(f"Pools: {state.get('pools', [])}")
    print(f"Temps: {state.get('temps', [])}")
    print(f"Network: {state.get('network', {})}")
    print(f"ZFS Activity: {state.get('zfs_activity', {})}")
    print(f"SMART: {state.get('smart', [])}")


def print_plugins(registry):
    summary = registry.summary()

    print("\nTruePanel Registry")
    print("==================")

    print("\nPlugins")
    print("-------")
    for plugin in summary["plugins"]:
        print(f"- {plugin['name']} {plugin['version']}")

    print("\nCollectors")
    print("----------")
    for collector in summary["collectors"]:
        print(f"- {collector}")

    print("\nDashboard Pages")
    print("---------------")
    for page in summary["dashboard_pages"]:
        print(f"- {page['id']}: {page['title']}")

    print("\nTheme Packs")
    print("-----------")
    for theme in summary["theme_packs"]:
        print(f"- {theme}")


def run_simulator(args, registry):
    collector = create_collector(
        kind="simulator",
        scenario=args.scenario,
        registry=registry,
    )

    step = 0

    while args.steps == 0 or step < args.steps:
        step += 1
        state = collector.update()
        print_state(state)
        time.sleep(args.delay)


def build_parser():
    parser = argparse.ArgumentParser(description="TruePanel command line")

    subcommands = parser.add_subparsers(dest="command")

    subcommands.add_parser("run", help="Run TruePanel")

    subcommands.add_parser("doctor", help="Run TruePanel diagnostics")

    subcommands.add_parser("plugins", help="Show loaded plugins")

    simulate = subcommands.add_parser("simulate", help="Run simulator")
    simulate.add_argument(
        "scenario",
        nargs="?",
        default="normal",
        choices=SCENARIOS,
        help="Simulator scenario",
    )
    simulate.add_argument(
        "--steps",
        type=int,
        default=20,
        help="Number of simulator updates. Use 0 to run forever.",
    )
    simulate.add_argument(
        "--delay",
        type=float,
        default=1.0,
        help="Delay between simulator updates in seconds.",
    )

    parser.add_argument(
        "--simulate",
        action="store_true",
        help="Legacy shortcut for simulator mode",
    )
    parser.add_argument(
        "--scenario",
        default="normal",
        choices=SCENARIOS,
        help="Legacy simulator scenario",
    )
    parser.add_argument(
        "--steps",
        type=int,
        default=20,
        help="Legacy simulator steps",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=1.0,
        help="Legacy simulator delay",
    )
    parser.add_argument(
        "--plugins",
        action="store_true",
        help="Legacy shortcut for plugin status",
    )
    parser.add_argument(
        "--doctor",
        action="store_true",
        help="Legacy shortcut for doctor diagnostics",
    )

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    registry = load_plugins()

    if args.doctor or args.command == "doctor":
        raise SystemExit(run_doctor())

    if args.plugins or args.command == "plugins":
        print_plugins(registry)
        return

    if args.simulate or args.command == "simulate":
        run_simulator(args, registry)
        return

    runpy.run_path("lcd-menu.py", run_name="__main__")


if __name__ == "__main__":
    main()
