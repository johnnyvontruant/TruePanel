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

        if self.scenario == "thermal":
            self.apply_thermal_scenario(state)
        elif self.scenario == "pool":
            self.apply_pool_scenario(state)
        elif self.scenario == "smart":
            self.apply_smart_scenario(state)
        elif self.scenario == "resilver":
            self.apply_resilver_scenario(state)
        elif self.scenario == "everything":
            self.apply_thermal_scenario(state)
            self.apply_pool_scenario(state)
            self.apply_smart_scenario(state)
            self.apply_resilver_scenario(state)

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

    def apply_thermal_scenario(self, state):
        hot_temp = min(65, 38 + self.tick_count * 2)

        state["temps"][0] = {
            "drive": "sda",
            "temp": hot_temp,
        }

    def apply_pool_scenario(self, state):
        if self.tick_count >= 5:
            state["pools"][0]["health"] = "DEGRADED"

    def apply_smart_scenario(self, state):
        if self.tick_count >= 4:
            state["smart"][1]["pending"] = self.tick_count - 3

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
