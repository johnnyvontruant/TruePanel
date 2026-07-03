#!/usr/bin/env python3

import json
import os
import platform
import subprocess
import threading
import time

import qnaplcd

from collector import TruePanelCollector
from truepanel.display.widgets import progress_bar
from truepanel.flightdeck.autopilot import AutoPilot
from truepanel.mission_control import MissionControl
from truepanel.mission_control.alert_manager import AlertManager
from truepanel.mission_control.display_manager import DisplayManager
from truepanel.mission_control.watchers.healthy import healthy_watcher
from truepanel.mission_control.watchers.pool import pool_watcher
from truepanel.mission_control.watchers.smart import smart_watcher
from truepanel.mission_control.watchers.thermal import thermal_watcher
from truepanel.mission_control.watchers.zfs import zfs_watcher
from truepanel.pages.fans import fan_pwm_page, fan_rpm_page


DISPLAY_TIMEOUT = 30
PORT = "/dev/ttyS1"
PORT_SPEED = 1200

lcd = None
lcd_timer = None
menu_item = 0

zfs_pools = []
ip_addresses = []

collector = TruePanelCollector()
mission = MissionControl()
alert_manager = AlertManager()
display_manager = DisplayManager(mission, alert_manager)
autopilot = AutoPilot(display_manager)

mission.register(pool_watcher)
mission.register(thermal_watcher)
mission.register(zfs_watcher)
mission.register(smart_watcher)
mission.register(healthy_watcher)


def lcd_on():
    global lcd_timer

    lcd.backlight(True)

    if lcd_timer:
        lcd_timer.cancel()

    lcd_timer = threading.Timer(DISPLAY_TIMEOUT, lambda: lcd.backlight(False))
    lcd_timer.start()


def shell(cmd):
    return subprocess.check_output(cmd, shell=True, universal_newlines=True).strip()


def get_state(max_age=5):
    last = collector.state.get("last_updated")
    now = time.time()

    if last is None or now - last > max_age:
        collector.update()

    return collector.state


def write_lines(line1, line2, delay=1):
    lcd.clear()
    lcd.write(0, [line1[:16], line2[:16]])
    time.sleep(delay)


def show_startup_splash():
    write_lines("TruePanel", "Flight Deck", 1)
    write_lines("Collector", "Online", 1)
    write_lines("Mission Ctrl", "Online", 1)
    write_lines("AutoPilot", "Online", 1)
    write_lines("Display", "Ready", 1)

    try:
        state = collector.update()
        frame = autopilot.frame(state)
        write_lines(frame.line1, frame.line2, 2)
    except Exception:
        write_lines("TruePanel", "Ready", 2)


def show_version():
    sys_name = platform.node()
    sys_vers = f"{platform.system()} ({platform.machine()})"

    lcd.clear()
    lcd.write(0, [sys_name[:16], sys_vers[:16]])


def show_truenas():
    if os.path.exists("/.dockerenv"):
        lines = ["TruePanel", "Docker Mode"]
    else:
        try:
            truenas = shell("cli -c 'system version'")
            truenas = truenas.split("-")
            lines = ["-".join(truenas[:-1]), truenas[-1]]
        except Exception:
            lines = ["TruePanel", "Native Mode"]

    lcd.clear()
    lcd.write(0, [lines[0][:16], lines[1][:16]])


def show_uptime():
    uptime = shell("uptime").split(",")
    up = " ".join(uptime[0].split()[2:]) + " " + uptime[1]
    load = os.getloadavg()

    lcd.clear()
    lcd.write(0, [f"Up: {up}"[:16], f"Load: {load[0]:.2f}"[:16]])


def show_cpu_ram():
    state = get_state()

    lcd.clear()
    lcd.write(0, [
        f"CPU {state.get('cpu_percent', 0)}%",
        f"RAM {state.get('ram_percent', 0)}%",
    ])


def show_pool_health():
    state = get_state()
    pools = state.get("pools", [])

    lcd.clear()

    if not pools:
        lcd.write(0, ["Pool Health", "No Pool Data"])
        return

    bad = [p for p in pools if p.get("health") != "ONLINE"]

    if bad:
        pool = bad[0]
        lcd.write(0, ["Pool Alert", f"{pool['name'][:8]} {pool['health'][:7]}"])
    else:
        lcd.write(0, ["Pool Health", "All Healthy"])


def add_ips_to_menu():
    def get_kind(iface):
        if "linkinfo" in iface:
            if "info_kind" in iface["linkinfo"]:
                return iface["linkinfo"]["info_kind"]

        return ""

    def get_ipv4(iface):
        if "addr_info" in iface:
            for addr in iface["addr_info"]:
                if addr["family"] == "inet":
                    return addr["local"]

        return "0.0.0.0"

    try:
        ip_json = json.loads(shell("ip -details -json address show"))
    except Exception:
        return

    ip_addresses.clear()

    for iface in ip_json:
        if iface["link_type"] == "loopback":
            continue

        if get_kind(iface) not in ["", "tun"]:
            continue

        ip_addresses.append((iface["ifname"], get_ipv4(iface)))

    while show_ip in menu:
        menu.remove(show_ip)

    for _ in ip_addresses:
        menu.append(show_ip)


def show_ip():
    ip_index = 0

    for index in range(menu_item):
        if menu[index] == show_ip:
            ip_index += 1

    lcd.clear()

    if not ip_addresses:
        lcd.write(0, ["Network", "No IP Data"])
        return

    lcd.write(0, [
        f"{ip_addresses[ip_index][0]}"[:16],
        f"{ip_addresses[ip_index][1]}"[:16],
    ])


def add_zpools_to_menu():
    pools = shell("zpool list").split("\n")

    zfs_pools.clear()

    for pool in pools[1:]:
        zfs_pools.append(pool.split())

    while show_zpool in menu:
        menu.remove(show_zpool)

    for _ in zfs_pools:
        menu.append(show_zpool)


def show_zpool():
    state = get_state()
    pools = state.get("pools", [])

    lcd.clear()

    if not pools:
        lcd.write(0, ["Storage", "No Pool Data"])
        return

    pool = pools[menu_item % len(pools)]
    name = pool.get("name", "pool")
    health = pool.get("health", "UNKNOWN")
    capacity = pool.get("capacity", "0%")

    try:
        pct = int(str(capacity).strip("%"))
    except Exception:
        pct = 0

    if health != "ONLINE":
        lcd.write(0, [f"{name[:8]} {health[:7]}", f"{pct}% Used"])
    else:
        lcd.write(0, [f"{name[:8]} {pct}%", progress_bar(pct)])


def show_drive_temps():
    state = get_state()
    temps = state.get("temps", [])

    lcd.clear()

    if not temps:
        lcd.write(0, ["Drive Temps", "No SMART Data"])
        return

    drive_info = temps[menu_item % len(temps)]
    drive = drive_info.get("drive", "disk")
    temp = drive_info.get("temp", 0)

    if temp >= 50:
        lcd.write(0, ["HOT DRIVE", f"{drive[:10]} {temp} C"])
    else:
        lcd.write(0, [f"Drive {drive[:10]}", f"Temp {temp} C"])


def show_fan_rpm():
    lcd.clear()
    lcd.write(0, fan_rpm_page())


def show_fan_pwm():
    lcd.clear()
    lcd.write(0, fan_pwm_page())


def show_mission_home():
    state = get_state()
    frame = autopilot.tick(state)

    lcd.clear()
    lcd.write(0, frame.lines)


def next_mission_dashboard():
    state = get_state()
    frame = autopilot.next(state)

    lcd.clear()
    lcd.write(0, frame.lines)


def previous_mission_dashboard():
    state = get_state()
    frame = autopilot.previous(state)

    lcd.clear()
    lcd.write(0, frame.lines)


def show_mission_control():
    state = collector.update()
    frame = display_manager.evaluate(state)

    lcd.clear()
    lcd.write(0, frame.lines)

    return frame


def show_event_queue():
    frame = display_manager.render_event_queue()

    lcd.clear()
    lcd.write(0, frame.lines)


def next_event_queue():
    frame = display_manager.next_event_queue()

    lcd.clear()
    lcd.write(0, frame.lines)


def show_alert_history():
    frame = display_manager.render_history()

    lcd.clear()
    lcd.write(0, frame.lines)


def next_alert_history():
    frame = display_manager.next_history()

    lcd.clear()
    lcd.write(0, frame.lines)


def show_alert_transition(frame):
    lcd.clear()
    lcd.write(0, frame.lines)
    time.sleep(frame.timeout)

    detail = display_manager.render_alert_detail(frame.event)
    lcd.clear()
    lcd.write(0, detail.lines)


def maybe_show_alert():
    state = collector.update()
    frame = display_manager.evaluate(state)

    if frame.interrupt:
        show_alert_transition(frame)
        time.sleep(frame.event.timeout)
        return True

    return False


menu = [
    show_mission_home,
    show_mission_control,
    show_event_queue,
    show_alert_history,
    show_truenas,
    show_version,
    show_uptime,
    show_cpu_ram,
    show_pool_health,
    show_zpool,
    show_drive_temps,
    show_fan_rpm,
    show_fan_pwm,
]


def response_handler(command, data):
    global menu_item

    prev_menu = menu_item

    if command == "Switch_Status":
        lcd_on()

        if menu[menu_item] == show_mission_home:
            if data == 0x01:
                previous_mission_dashboard()
                return

            if data == 0x02:
                next_mission_dashboard()
                return

        if menu[menu_item] == show_alert_history:
            if data in (0x01, 0x02):
                next_alert_history()
                return

        if menu[menu_item] == show_event_queue:
            if data in (0x01, 0x02):
                next_event_queue()
                return

        if data == 0x01:
            menu_item = (menu_item - 1) % len(menu)

        if data == 0x02:
            menu_item = (menu_item + 1) % len(menu)

    if prev_menu != menu_item:
        menu[menu_item]()


def main():
    global lcd

    lcd = qnaplcd.QnapLCD(PORT, PORT_SPEED, response_handler)
    lcd_on()
    lcd.reset()
    lcd.clear()

    show_startup_splash()

    quit_requested = False

    while not quit_requested:
        add_ips_to_menu()

        if not maybe_show_alert():
            menu[menu_item]()
            time.sleep(5 if menu[menu_item] == show_mission_home else 30)

    lcd.backlight(False)


main()
