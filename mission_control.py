from truepanel.mission_control import MissionControl
from truepanel.mission_control.watchers.healthy import healthy_watcher
from truepanel.mission_control.watchers.pool import pool_watcher
from truepanel.mission_control.watchers.thermal import thermal_watcher
from truepanel.mission_control.watchers.zfs import zfs_watcher


if __name__ == "__main__":
    mission = MissionControl()

    mission.register(pool_watcher)
    mission.register(thermal_watcher)
    mission.register(zfs_watcher)
    mission.register(healthy_watcher)

    event = mission.evaluate({
        "pools": [
            {"name": "tank", "health": "ONLINE"}
        ],
        "temps": [
            {"drive": "sda", "temp": 37},
            {"drive": "nvme0n1", "temp": 44}
        ],
        "zfs_activity": {
            "scrub_running": True,
            "resilver_running": False,
            "percent": 42,
            "remaining": None,
            "problem": False,
        }
    })

    print(event)
