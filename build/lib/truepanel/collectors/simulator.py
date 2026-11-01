"""
Simulator Collector

Produces fake-but-realistic NAS states for development, demos, and tests.
"""

import time

from .base import Collector


class SimulatorCollector(Collector):
    name = "simulator"

    def __init__(self, scenario="normal"):
        self.scenario = scenario
        self.tick_count = 0
        self.started_at = time.time()

    def update(self):
        self.tick_count += 1

        state = self.base_state()

        scenario = self.scenario

        if scenario == "thermal":
            self.apply_thermal_scenario(state)
        elif scenario == "pool":
            self.apply_pool_scenario(state)
        elif scenario == "smart":
            self.apply_smart_scenario(state)
        elif scenario == "resilver":
            self.apply_resilver_scenario(state)
        elif scenario == "network":
            self.apply_network_scenario(state)
        elif scenario == "capacity":
            self.apply_capacity_scenario(state)
        elif scenario == "quiet-night":
            self.apply_quiet_night_scenario(state)
        elif scenario == "everything":
            self.apply_thermal_scenario(state)
            self.apply_pool_scenario(state)
            self.apply_smart_scenario(state)
            self.apply_resilver_scenario(state)
            self.apply_network_scenario(state)
            self.apply_capacity_scenario(state)

        state["last_updated"] = time.time()
        return state

    def base_state(self):
        cpu = min(95, 10 + (self.tick_count * 3) % 70)
        ram = min(90, 35 + (self.tick_count * 2) % 45)

        return {
            "hostname": "SimPanel",
            "cpu_percent": cpu,
            "ram_percent": ram,
            "network": {
                "sim0": {
                    "download_mb": round(4.5 + self.tick_count * 0.2, 1),
                    "upload_mb": round(1.2 + self.tick_count * 0.1, 1),
                }
            },
            "pools": [
                {
                    "name": "tank",
                    "size": "10T",
                    "used": "4T",
                    "free": "6T",
                    "capacity": "40%",
                    "health": "ONLINE",
                }
            ],
            "temps": [
                {"drive": "sda", "temp": 36},
                {"drive": "sdb", "temp": 38},
                {"drive": "sdc", "temp": 37},
            ],
            "arc": {
                "available": True,
                "size_gb": 8.4,
                "hit_percent": 96.2,
                "hits": 100000,
                "misses": 4000,
            },
            "zfs_activity": {
                "scrub_running": False,
                "resilver_running": False,
                "percent": None,
                "remaining": None,
                "status_line": "",
                "problem": False,
                "problem_line": "",
            },
            "smart": [
                {
                    "drive": "sda",
                    "health": "PASSED",
                    "reallocated": 0,
                    "pending": 0,
                    "offline_uncorrectable": 0,
                    "reported_uncorrect": 0,
                    "media_errors": 0,
                    "critical_warning": "0x00",
                },
                {
                    "drive": "sdb",
                    "health": "PASSED",
                    "reallocated": 0,
                    "pending": 0,
                    "offline_uncorrectable": 0,
                    "reported_uncorrect": 0,
                    "media_errors": 0,
                    "critical_warning": "0x00",
                },
            ],
            "last_updated": None,
        }

    def timeline_value(self, points):
        value = points[0][1]

        for tick, candidate in points:
            if self.tick_count >= tick:
                value = candidate

        return value

    def apply_thermal_scenario(self, state):
        hot_temp = self.timeline_value([
            (1, 40),
            (3, 45),
            (5, 51),
            (8, 56),
            (12, 61),
        ])

        state["temps"][0] = {
            "drive": "sda",
            "temp": hot_temp,
        }

    def apply_pool_scenario(self, state):
        health = self.timeline_value([
            (1, "ONLINE"),
            (5, "DEGRADED"),
            (10, "FAULTED"),
        ])

        state["pools"][0]["health"] = health

    def apply_smart_scenario(self, state):
        pending = self.timeline_value([
            (1, 0),
            (4, 1),
            (6, 3),
            (9, 8),
        ])

        state["smart"][1]["pending"] = pending

        if self.tick_count >= 8:
            state["smart"][1]["health"] = "FAILED"

    def apply_resilver_scenario(self, state):
        percent = min(99, self.tick_count * 7)

        state["zfs_activity"] = {
            "scrub_running": False,
            "resilver_running": True,
            "percent": percent,
            "remaining": "simulated time remaining",
            "status_line": f"resilver in progress, {percent}% done",
            "problem": False,
            "problem_line": "",
        }

    def apply_network_scenario(self, state):
        state["network"]["sim0"] = {
            "download_mb": round(25 + self.tick_count * 3.5, 1),
            "upload_mb": round(8 + self.tick_count * 1.7, 1),
        }

    def apply_capacity_scenario(self, state):
        percent = min(96, 70 + self.tick_count * 2)

        state["pools"][0]["capacity"] = f"{percent}%"
        state["pools"][0]["used"] = f"{round(percent / 10, 1)}T"
        state["pools"][0]["free"] = f"{round(10 - percent / 10, 1)}T"

    def apply_quiet_night_scenario(self, state):
        state["hostname"] = "NightPanel"
        state["cpu_percent"] = 5
        state["ram_percent"] = 28
        state["network"]["sim0"] = {
            "download_mb": 0.1,
            "upload_mb": 0.0,
        }
