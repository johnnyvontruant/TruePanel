from collector import TruePanelCollector

from truepanel.mission_control import MissionControl
from truepanel.mission_control.alert_manager import AlertManager
from truepanel.mission_control.display_manager import DisplayManager
from truepanel.mission_control.renderer import render_event
from truepanel.mission_control.watchers.healthy import healthy_watcher
from truepanel.mission_control.watchers.pool import pool_watcher
from truepanel.mission_control.watchers.smart import smart_watcher
from truepanel.mission_control.watchers.thermal import thermal_watcher
from truepanel.mission_control.watchers.zfs import zfs_watcher


if __name__ == "__main__":
    mission = MissionControl()

    mission.register(pool_watcher)
    mission.register(thermal_watcher)
    mission.register(zfs_watcher)
    mission.register(smart_watcher)
    mission.register(healthy_watcher)

    collector = TruePanelCollector()
    alert_manager = AlertManager()
    display_manager = DisplayManager(mission, alert_manager)

    state = collector.update()

    event = mission.evaluate(state)
    frame = display_manager.evaluate(state)

    print(event)
    print(render_event(event))
    print(frame)
