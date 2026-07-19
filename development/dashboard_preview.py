#!/usr/bin/env python3

from pathlib import Path
import sys

import yaml

sys.path.insert(
    0,
    str(Path(__file__).resolve().parent.parent),
)

from truepanel.mission_control.display_manager import DisplayManager


class DummyRegistry:
    dashboard_pages = []


class DummyMission:
    queue = []
    history = []

    @staticmethod
    def evaluate(state):
        return None


class DummyAlerts:
    @staticmethod
    def get_history():
        return []

    @staticmethod
    def get_active_alerts():
        return []

    @staticmethod
    def current_alert():
        return None


config = yaml.safe_load(
    Path("truepanel.yaml").read_text()
) or {}

display = DisplayManager(
    mission=DummyMission(),
    alert_manager=DummyAlerts(),
    config=config,
    registry=DummyRegistry(),
)

sample_state = {
    "hostname": "BattleStation",
    "version": "25.10.4",
    "uptime": "12 days",
    "cpu_percent": 37,
    "ram_percent": 54,
    "temps": [
        {"drive": "sda", "temp": 39},
        {"drive": "sdb", "temp": 42},
    ],
    "pools": [
        {
            "name": "tank",
            "health": "ONLINE",
            "capacity": "72%",
        }
    ],
    "smart": [
        {
            "drive": "sda",
            "health": "PASSED",
            "pending": 0,
            "offline_uncorrectable": 0,
            "media_errors": 0,
            "critical_warning": "0x00",
        },
        {
            "drive": "sdb",
            "health": "PASSED",
            "pending": 0,
            "offline_uncorrectable": 0,
            "media_errors": 0,
            "critical_warning": "0x00",
        },
    ],
    "zfs_activity": {
        "read_bytes_per_sec": 24 * 1024 * 1024,
        "write_bytes_per_sec": 3 * 1024 * 1024,
    },
}

print()
print("========== TRUEPANEL DASHBOARD PREVIEW ==========")

for index, page in enumerate(display.dashboard_pages, start=1):
    page_id = page.get("id", "unknown")
    renderer = page.get("renderer")

    print()
    print(f"[{index:02}] {page_id.upper()}")
    print("+----------------+")

    try:
        frame = renderer(sample_state)

        line1 = str(frame.line1)[:16].ljust(16)
        line2 = str(frame.line2)[:16].ljust(16)

        print(f"|{line1}|")
        print(f"|{line2}|")

    except Exception as error:
        message = f"{type(error).__name__}"
        detail = str(error)

        print(f"|{'PREVIEW ERROR':^16}|")
        print(f"|{message[:16]:<16}|")
        print()
        print(f"    {detail}")

    print("+----------------+")

print()
print("=================================================")
