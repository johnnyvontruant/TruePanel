#!/usr/bin/env python3

"""
TruePanel launcher.

Default behavior safely runs the existing working LCD menu.

Simulator mode runs a collector without touching LCD hardware.
"""

import argparse
import runpy
import time

from truepanel.collectors import create_collector


def print_state(state):
    print("\nTruePanel Simulator")
    print("-------------------")
    print(f"Host: {state.get('hostname', 'unknown')}")
    print(f"CPU: {state.get('cpu_percent', 0)}%")
    print(f"RAM: {state.get('ram_percent', 0)}%")
    print(f"Pools: {state.get('pools', [])}")
    print(f"Temps: {state.get('temps', [])}")
    print(f"ZFS Activity: {state.get('zfs_activity', {})}")
    print(f"SMART: {state.get('smart', [])}")


def run_simulator(args):
    collector = create_collector(
        kind="simulator",
        scenario=args.scenario,
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
        "--scenario",
        default="normal",
        choices=["normal", "thermal", "pool", "smart", "resilver", "everything"],
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

    if args.simulate:
        run_simulator(args)
        return

    runpy.run_path("lcd-menu.py", run_name="__main__")


if __name__ == "__main__":
    main()
