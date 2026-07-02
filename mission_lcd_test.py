#!/usr/bin/env python3
import time

import qnaplcd
from collector import TruePanelCollector
from truepanel.mission_control import MissionControl
from truepanel.mission_control.renderer import render_event
from truepanel.mission_control.watchers.healthy import healthy_watcher
from truepanel.mission_control.watchers.pool import pool_watcher
from truepanel.mission_control.watchers.smart import smart_watcher
from truepanel.mission_control.watchers.thermal import thermal_watcher
from truepanel.mission_control.watchers.zfs import zfs_watcher


PORT = "/dev/ttyS1"
SPEED = 1200


mission = MissionControl()
mission.register(pool_watcher)
mission.register(thermal_watcher)
mission.register(zfs_watcher)
mission.register(smart_watcher)
mission.register(healthy_watcher)

collector = TruePanelCollector()

lcd = qnaplcd.QnapLCD(PORT, SPEED)
lcd.backlight(True)

state = collector.update()
event = mission.evaluate(state)
lines = render_event(event)

lcd.clear()
lcd.write(0, lines)

print(event)
print(lines)

time.sleep(10)
