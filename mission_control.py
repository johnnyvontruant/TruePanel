from collector import TruePanelCollector
from truepanel.mission_control import MissionControl
from truepanel.mission_control.watchers.healthy import healthy_watcher
from truepanel.mission_control.watchers.pool import pool_watcher
from truepanel.mission_control.watchers.thermal import thermal_watcher
from truepanel.mission_control.watchers.zfs import zfs_watcher
from truepanel.mission_control.watchers.smart import smart_watcher


if __name__ == "__main__":
    mission = MissionControl()

    mission.register(pool_watcher)
    mission.register(thermal_watcher)
    mission.register(zfs_watcher)
    mission.register(smart_watcher)
    mission.register(healthy_watcher)

    collector = TruePanelCollector()

    state = collector.update()

    event = mission.evaluate(state)

    print(event)

