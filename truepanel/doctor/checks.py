"""
TruePanel Doctor

Safe diagnostics for configuration, plugins, collectors, and runtime readiness.
"""

import shutil
import sys
from pathlib import Path

from truepanel.config.loader import load_config
from truepanel.plugins import load_plugins


def ok(name, detail="OK"):
    return {"status": "OK", "name": name, "detail": detail}


def warn(name, detail):
    return {"status": "WARN", "name": name, "detail": detail}


def fail(name, detail):
    return {"status": "FAIL", "name": name, "detail": detail}


def check_python():
    version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"

    if sys.version_info.major == 3 and sys.version_info.minor >= 9:
        return ok("Python", version)

    return fail("Python", f"{version} detected, Python 3.9+ recommended")


def check_config():
    path = Path("truepanel.yaml")

    if not path.exists():
        return warn("Configuration", "truepanel.yaml not found, using defaults")

    try:
        config = load_config(path)
    except Exception as error:
        return fail("Configuration", str(error))

    theme_pack = config.get("theme_pack", "default")
    return ok("Configuration", f"theme_pack={theme_pack}")


def check_theme_pack():
    config = load_config()
    theme_pack = config.get("theme_pack", "default")
    theme_path = Path("truepanel/themes/packs") / f"{theme_pack}.yaml"

    if theme_path.exists():
        return ok("Theme Pack", theme_pack)

    return warn("Theme Pack", f"{theme_pack} not found, defaults may be used")


def check_plugins():
    try:
        registry = load_plugins()
    except Exception as error:
        return fail("Plugins", str(error))

    count = len(registry.plugins)
    collectors = ", ".join(registry.collectors.keys()) or "none"

    return ok("Plugins", f"{count} loaded, collectors: {collectors}")


def check_required_commands():
    commands = ["smartctl", "zpool", "lsblk"]
    missing = [command for command in commands if shutil.which(command) is None]

    if missing:
        return warn("System Commands", "missing: " + ", ".join(missing))

    return ok("System Commands", "smartctl, zpool, lsblk")


def check_collector_import():
    try:
        from collector import TruePanelCollector  # noqa: F401
    except Exception as error:
        return fail("TrueNAS Collector", str(error))

    return ok("TrueNAS Collector", "importable")


def check_simulator():
    try:
        from truepanel.collectors import create_collector

        collector = create_collector(kind="simulator", scenario="normal")
        state = collector.update()
    except Exception as error:
        return fail("Simulator", str(error))

    if "cpu_percent" not in state or "pools" not in state:
        return fail("Simulator", "state missing expected keys")

    return ok("Simulator", "state generated")


def check_mission_control_imports():
    modules = [
        "truepanel.mission_control.engine",
        "truepanel.mission_control.alert_manager",
        "truepanel.mission_control.display_manager",
        "truepanel.flightdeck.autopilot",
    ]

    for module in modules:
        try:
            __import__(module)
        except Exception as error:
            return fail("Mission Stack", f"{module}: {error}")

    return ok("Mission Stack", "imports clean")


def run_checks():
    return [
        check_python(),
        check_config(),
        check_theme_pack(),
        check_plugins(),
        check_required_commands(),
        check_collector_import(),
        check_simulator(),
        check_mission_control_imports(),
    ]


def print_result(result):
    symbol = {
        "OK": "✓",
        "WARN": "!",
        "FAIL": "✗",
    }.get(result["status"], "?")

    print(f"{symbol} {result['name']:<20} {result['detail']}")


def run_doctor():
    print("\nTruePanel Doctor")
    print("================\n")

    results = run_checks()

    for result in results:
        print_result(result)

    failures = [result for result in results if result["status"] == "FAIL"]
    warnings = [result for result in results if result["status"] == "WARN"]

    print("\nMission Status")
    print("--------------")

    if failures:
        print("MISSION BLOCKED")
        return 1

    if warnings:
        print("MISSION DEGRADED")
        return 0

    print("MISSION READY")
    return 0
