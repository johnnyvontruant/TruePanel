#!/usr/bin/env python3

"""
TruePanel launcher.

Default behavior safely runs the existing working LCD menu.

Simulator mode runs a collector without touching LCD hardware.
Plugin status mode shows the active registry.
Doctor mode runs safe system diagnostics.
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


def parse_args():
    parser = argparse.ArgumentParser(description="TruePanel launcher")

    parser.add_argument(
        "--simulate",
        action="store_true",
        help="Run TruePanel with simulated collector data",
    )

    parser.add_argument(
        "--plugins",
        action="store_true",
        help="Show loaded TruePanel plugins and registry entries",
    )

    parser.add_argument(
        "--doctor",
        action="store_true",
        help="Run TruePanel diagnostics",
    )

    parser.add_argument(
        "--scenario",
        default="normal",
        choices=SCENARIOS,
        help="Simulator scenario to run",
    )

    parser.add_argument(
        "--steps",
        type=int,
        default=20,
        help="Number of simulator updates to run. Use 0 to run forever.",
    )

    parser.add_argument(
        "--delay",
        type=float,
        default=1.0,
        help="Delay between simulator updates in seconds",
    )

    return parser.parse_args()


def main():
    args = parse_args()
    registry = load_plugins()

    if args.doctor:
        raise SystemExit(run_doctor())

    if args.plugins:
        print_plugins(registry)
        return

    if args.simulate:
        run_simulator(args, registry)
        return

    runpy.run_path("lcd-menu.py", run_name="__main__")


if __name__ == "__main__":
    main()
