"""
TruePanel CLI
"""

import argparse
from pathlib import Path
import platform
import runpy
import time

from truepanel import __version__
from truepanel.collectors import create_collector
from truepanel.doctor import run_doctor
from truepanel.logging import setup_logging
from truepanel.config.loader import load_config
from truepanel.hardware import Buzzer
from truepanel.history import TelemetryRecorder
from truepanel.themes import Theme, discover_theme_packs, load_theme_pack, validate_theme_pack
from truepanel.plugins import load_plugins
from truepanel.plugins.commands import add_plugin_subcommands, handle_plugin_command


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


def print_version(registry):
    print("\nTruePanel")
    print("=========")
    print(f"Version: {__version__}")
    print(f"Python:  {platform.python_version()}")
    print(f"System:  {platform.system()} {platform.machine()}")
    print(f"Plugins: {len(registry.plugins)}")
    print()
    print("Mission Ready")


def run_simulator(args, registry):
    collector = create_collector(
        kind="simulator",
        scenario=args.scenario,
        registry=registry,
    )

    recorder = None

    if getattr(args, "record_history", False):
        config = load_config()
        history_config = dict(config.get("history", {}))

        if getattr(args, "history_path", None):
            history_config["path"] = args.history_path

        recorder = TelemetryRecorder(history_config)

    step = 0

    while args.steps == 0 or step < args.steps:
        step += 1
        state = collector.update()

        if recorder is not None:
            # Recording was explicitly requested for this simulator run,
            # so preserve every generated step regardless of interval.
            recorder.record(state, force=True)

        print_state(state)
        time.sleep(args.delay)

    if recorder is not None:
        stats = recorder.stats()
        print("\nHistory Recording")
        print("-----------------")
        print(f"Samples: {stats['samples']}")
        print(f"Path: {stats['path']}")


def print_theme_preview(pack_id):
    pack = load_theme_pack(pack_id)

    if pack is None:
        raise SystemExit(f"Unknown theme pack: {pack_id}")

    errors = validate_theme_pack(pack)

    if errors:
        print(f"Theme {pack_id} is invalid:")
        for error in errors:
            print(f"- {error}")
        raise SystemExit(1)

    config = load_config()
    config["theme"] = pack.theme
    config["graphics"] = pack.graphics
    theme = Theme(config)

    print(f"\n{pack.name}")
    print("=" * len(pack.name))
    print(pack.description)
    print()
    print("+----------------+")
    print(
        "|"
        + (
            theme.status(10)
            + " "
            + theme.text("mission_ready", "MISSION READY")
        )[:16].ljust(16)
        + "|"
    )
    print(
        "|"
        + theme.text("all_systems_go", "All Systems GO")[:16].center(16)
        + "|"
    )
    print("+----------------+")
    print("|CPU 64% RAM 82% |")
    print("|" + theme.bar(68, 16) + "|")
    print("+----------------+")


def list_themes():
    print("\nTruePanel Theme Packs")
    print("=====================")

    for pack in discover_theme_packs():
        print(f"- {pack.pack_id}: {pack.name}")
        if pack.description:
            print(f"  {pack.description}")


def set_theme(pack_id, config_path="truepanel.yaml"):
    pack = load_theme_pack(pack_id)

    if pack is None:
        raise SystemExit(f"Unknown theme pack: {pack_id}")

    errors = validate_theme_pack(pack)

    if errors:
        raise SystemExit("; ".join(errors))

    path = Path(config_path)
    text = path.read_text() if path.exists() else ""

    lines = text.splitlines()
    replaced = False

    for index, line in enumerate(lines):
        if line.strip().startswith("theme_pack:"):
            lines[index] = f"theme_pack: {pack_id}"
            replaced = True
            break

    if not replaced:
        lines.insert(0, f"theme_pack: {pack_id}")

    path.write_text("\n".join(lines).rstrip() + "\n")
    print(f"Theme selected: {pack.name}")
    print("Restart TruePanel to apply it:")
    print("  systemctl restart truepanel")


def run_buzzer_test(args):
    config = load_config()
    buzzer_config = config.get("buzzer", {})
    buzzer = Buzzer(buzzer_config)

    if buzzer.beep(args.pattern, force=True):
        print(f"Buzzer {args.pattern} test sent")
    else:
        raise SystemExit("Buzzer test failed; check logs and configuration")

def build_parser():
    parser = argparse.ArgumentParser(description="TruePanel command line")

    parser.add_argument(
        "--log-level",
        default="INFO",
        help="Logging level: DEBUG, INFO, WARNING, ERROR",
    )

    subcommands = parser.add_subparsers(dest="command")

    subcommands.add_parser("run", help="Run TruePanel")
    subcommands.add_parser("doctor", help="Run TruePanel diagnostics")
    add_plugin_subcommands(subcommands)
    subcommands.add_parser("version", help="Show TruePanel version")

    themes = subcommands.add_parser("themes", help="Manage theme packs")
    theme_commands = themes.add_subparsers(dest="theme_command")
    theme_commands.add_parser("list", help="List installed themes")

    theme_preview = theme_commands.add_parser("preview", help="Preview a theme")
    theme_preview.add_argument("theme")

    theme_set = theme_commands.add_parser("set", help="Select a theme")
    theme_set.add_argument("theme")

    buzzer = subcommands.add_parser("buzzer", help="Test the NAS buzzer")
    buzzer.add_argument(
        "pattern",
        choices=["short", "long"],
        nargs="?",
        default="short",
    )

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
    simulate.add_argument(
        "--record-history",
        action="store_true",
        help="Record every generated simulator step to history.",
    )
    simulate.add_argument(
        "--history-path",
        help="Override the configured history file for this run.",
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

    logger = setup_logging(args.log_level)
    logger.info("TruePanel CLI starting")

    registry = load_plugins()

    if args.command == "version":
        print_version(registry)
        return

    if args.command == "themes":
        if args.theme_command == "preview":
            print_theme_preview(args.theme)
        elif args.theme_command == "set":
            set_theme(args.theme)
        else:
            list_themes()
        return

    if args.command == "buzzer":
        run_buzzer_test(args)
        return

    if args.doctor or args.command == "doctor":
        raise SystemExit(run_doctor())

    if args.command == "plugins":
        raise SystemExit(handle_plugin_command(args))

    if args.plugins:
        print_plugins(registry)
        return

    if args.simulate or args.command == "simulate":
        run_simulator(args, registry)
        return

    logger.info("Starting LCD menu")
    runpy.run_path("lcd-menu.py", run_name="__main__")


if __name__ == "__main__":
    main()
