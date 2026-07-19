from collector import TruePanelCollector

from truepanel.config.loader import load_config
from truepanel.mission_control import MissionControl
from truepanel.mission_control.alert_manager import AlertManager
from truepanel.mission_control.display_manager import DisplayManager
from truepanel.mission_control.renderer import render_event
from truepanel.mission_control.watchers.healthy import healthy_watcher
from truepanel.mission_control.watchers.pool import pool_watcher
from truepanel.mission_control.watchers.smart import smart_watcher
from truepanel.mission_control.watchers.storage_health import (
    build_storage_health_watcher,
)
from truepanel.mission_control.watchers.thermal import thermal_watcher
from truepanel.mission_control.watchers.zfs import zfs_watcher


if __name__ == "__main__":
    mission = MissionControl()
    config = load_config()
    storage_health_watcher = build_storage_health_watcher(config)

    mission.register(pool_watcher)
    mission.register(thermal_watcher)
    mission.register(zfs_watcher)
    mission.register(smart_watcher)

    if storage_health_watcher is not None:
        mission.register(storage_health_watcher)

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
