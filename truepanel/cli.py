"""
TruePanel CLI
"""

import argparse
import platform
import runpy
import sys
import time
from pathlib import Path

from truepanel import __version__
from truepanel.collectors import create_collector
from truepanel.compatibility import run_compatibility
from truepanel.config.loader import load_config
from truepanel.diagnostics.a125 import main as run_a125_diagnostics
from truepanel.doctor import run_doctor
from truepanel.hardware import Buzzer
from truepanel.hardware.commands import (
    add_hardware_subcommands,
    handle_hardware_command,
)
from truepanel.history import TelemetryRecorder
from truepanel.host.commands import (
    add_host_subcommands,
    handle_host_command,
)
from truepanel.lab.commands import main as run_stargate_lab
from truepanel.logging import setup_logging
from truepanel.plugins import load_plugins
from truepanel.plugins.commands import add_plugin_subcommands, handle_plugin_command
from truepanel.repair import run_repair
from truepanel.themes import (
    Theme,
    discover_theme_packs,
    load_theme_pack,
    validate_theme_pack,
)
from truepanel.upgrade import run_upgrade
from truepanel.verify import run_verify
from truepanel.web.operations import (
    add_mission_control_subcommands,
    handle_mission_control_command,
)

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
    verify = subcommands.add_parser(
        "verify",
        help="Verify the TruePanel installation",
    )
    verify.add_argument(
        "--root",
        dest="verify_root",
        help=(
            "Installation root to verify; defaults to "
            "TRUEPANEL_ROOT or the running TruePanel tree"
        ),
    )
    compatibility = subcommands.add_parser(
        "compatibility",
        help="Survey passive TruePanel compatibility",
    )
    compatibility_mode = (
        compatibility.add_mutually_exclusive_group()
    )
    compatibility_mode.add_argument(
        "--json",
        action="store_true",
        dest="compatibility_json",
        help="Output machine-readable JSON",
    )
    compatibility_mode.add_argument(
        "--support-bundle",
        action="store_true",
        dest="compatibility_support_bundle",
        help="Write a privacy-safe support bundle",
    )
    compatibility.add_argument(
        "--output",
        dest="compatibility_output",
        help=(
            "Support bundle destination; valid only with "
            "--support-bundle"
        ),
    )
    add_plugin_subcommands(subcommands)
    add_hardware_subcommands(subcommands)
    add_host_subcommands(subcommands)
    add_mission_control_subcommands(subcommands)
    subcommands.add_parser("version", help="Show TruePanel version")

    upgrade = subcommands.add_parser(
        "upgrade",
        help="Plan or stage a TruePanel upgrade",
    )
    upgrade.add_argument(
        "--source",
        dest="upgrade_source",
        help="Source tree; defaults to the current directory",
    )
    upgrade.add_argument(
        "--root",
        dest="upgrade_root",
        help=(
            "Deployed installation root; defaults to "
            "TRUEPANEL_ROOT or the running TruePanel tree"
        ),
    )
    upgrade.add_argument(
        "--stage-root",
        dest="upgrade_stage_root",
        help="Explicit staging directory",
    )
    upgrade.add_argument(
        "--backup-root",
        dest="upgrade_backup_root",
        help=(
            "Explicit backup directory for promotion "
            "or selected backup for rollback"
        ),
    )
    upgrade.add_argument(
        "--safety-backup-root",
        dest="upgrade_safety_backup_root",
        help=(
            "Explicit pre-rollback safety backup "
            "directory"
        ),
    )
    upgrade.add_argument(
        "--confirm",
        dest="upgrade_confirmation",
        help=(
            "Required confirmation phrase for guarded "
            "upgrade operations"
        ),
    )
    upgrade_mode = upgrade.add_mutually_exclusive_group(
        required=True
    )
    upgrade_mode.add_argument(
        "--dry-run",
        action="store_true",
        help="Show the upgrade plan without writing files",
    )
    upgrade_mode.add_argument(
        "--stage-only",
        action="store_true",
        help="Create and validate a staging tree only",
    )
    upgrade_mode.add_argument(
        "--promote",
        action="store_true",
        help=(
            "Promote a validated stage with backup "
            "and automatic rollback"
        ),
    )
    upgrade_mode.add_argument(
        "--cleanup",
        action="store_true",
        help=(
            "List or remove completed upgrade assets "
            "without touching services"
        ),
    )
    upgrade_mode.add_argument(
        "--rollback",
        action="store_true",
        help=(
            "Restore an explicit retained backup with "
            "pre-rollback recovery protection"
        ),
    )

    repair = subcommands.add_parser(
        "repair",
        help="Repair the TruePanel lifecycle installation",
    )
    repair.add_argument(
        "--root",
        dest="repair_root",
        help=(
            "Installation root to repair; defaults to "
            "TRUEPANEL_ROOT or the running TruePanel tree"
        ),
    )
    repair.add_argument(
        "--dry-run",
        action="store_true",
        help="Show planned repairs without changing the system",
    )

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
    # Project Stargate Laboratory.
    if len(sys.argv) >= 2 and sys.argv[1] == "lab":
        raise SystemExit(
            run_stargate_lab(sys.argv[2:])
        )
    # Project Stargate diagnostic subcommand.
    if len(sys.argv) >= 3 and sys.argv[1:3] == ["doctor", "a125"]:
        raise SystemExit(
            run_a125_diagnostics(sys.argv[3:])
        )
    parser = build_parser()
    args = parser.parse_args()

    logger = setup_logging(args.log_level)
    logger.info("TruePanel CLI starting")

    if args.command == "compatibility":
        if (
            args.compatibility_output
            and not args.compatibility_support_bundle
        ):
            parser.error(
                "--output requires --support-bundle"
            )

        raise SystemExit(
            run_compatibility(
                json_output=args.compatibility_json,
                support_bundle=(
                    args.compatibility_support_bundle
                ),
                output=args.compatibility_output,
            )
        )

    if args.command == "verify":
        verify_root = (
            Path(args.verify_root).resolve()
            if args.verify_root
            else None
        )
        raise SystemExit(
            run_verify(
                root=verify_root,
            )
        )

    if args.command == "upgrade":
        upgrade_root = (
        Path(
            args.upgrade_root
        ).resolve()
        if args.upgrade_root
        else None
    )

        upgrade_stage_root = (
            Path(
                args.upgrade_stage_root
            ).resolve()
            if args.upgrade_stage_root
            else None
        )

        if args.promote:
            from truepanel.upgrade import (
                run_promotion,
            )

            raise SystemExit(
                run_promotion(
                    stage_root=upgrade_stage_root,
                    deploy_root=upgrade_root,
                    backup_root=(
                        Path(
                            args.upgrade_backup_root
                        ).resolve()
                        if args.upgrade_backup_root
                        else None
                    ),
                    confirmation=(
                        args.upgrade_confirmation
                    ),
                )
            )

        if args.cleanup:
            from truepanel.upgrade import (
                run_cleanup,
            )

            raise SystemExit(
                run_cleanup(
                    deploy_root=upgrade_root,
                    confirmation=(
                        args.upgrade_confirmation
                    ),
                )
            )

        if args.rollback:
            from truepanel.upgrade import (
                run_rollback,
            )

            raise SystemExit(
                run_rollback(
                    deploy_root=upgrade_root,
                    selected_backup_root=(
                        Path(
                            args.upgrade_backup_root
                        ).resolve()
                        if args.upgrade_backup_root
                        else None
                    ),
                    safety_backup_root=(
                        Path(
                            args.upgrade_safety_backup_root
                        ).resolve()
                        if args.upgrade_safety_backup_root
                        else None
                    ),
                    confirmation=(
                        args.upgrade_confirmation
                    ),
                )
            )

        raise SystemExit(
            run_upgrade(
                source_root=(
                    Path(
                        args.upgrade_source
                    ).resolve()
                    if args.upgrade_source
                    else None
                ),
                deploy_root=upgrade_root,
                stage_root=upgrade_stage_root,
                dry_run=args.dry_run,
                stage_only=args.stage_only,
            )
        )

    if args.command == "repair":
        repair_root = (
            Path(args.repair_root).resolve()
            if args.repair_root
            else None
        )
        raise SystemExit(
            run_repair(
                root=repair_root,
                dry_run=args.dry_run,
            )
        )

    mission_control_result = (
        handle_mission_control_command(args)
    )

    if mission_control_result is not None:
        raise SystemExit(
            mission_control_result
        )

    host_result = handle_host_command(args)

    if host_result is not None:
        raise SystemExit(
            host_result
        )

    registry = load_plugins()

    if handle_hardware_command(args):
        return 0

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
    lcd_menu_path = (
        Path(__file__).resolve().parents[1]
        / "lcd-menu.py"
    )
    runpy.run_path(
        str(lcd_menu_path),
        run_name="__main__",
    )


if __name__ == "__main__":
    main()
