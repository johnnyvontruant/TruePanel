#!/usr/bin/env python3

import json
import logging
import os
import platform
import signal
import subprocess
import threading
import time

import qnaplcd
from collector import TruePanelCollector
from truepanel.config.loader import load_config
from truepanel.display.widgets import progress_bar
from truepanel.flightdeck.autopilot import AutoPilot
from truepanel.hardware import Buzzer
from truepanel.hardware.bay_led_animation import (
    build_bay_led_startup_animation,
)
from truepanel.hardware.lcd_display_status_bridge import (
    LCDDisplayStatusBridge,
)
from truepanel.hardware.lcd_reader_status_bridge import (
    LCDReaderStatusBridge,
)
from truepanel.history import (
    TelemetryRecorder,
)
from truepanel.host import (
    HostAgentApplicationHooks,
    build_host_agent_bootstrap,
    build_host_agent_runtime_from_bootstrap,
)
from truepanel.mission_control import MissionControl
from truepanel.mission_control.alert_manager import AlertManager
from truepanel.mission_control.display_manager import DisplayManager
from truepanel.mission_control.watchers.fan_health import (
    build_fan_health_watcher,
)
from truepanel.mission_control.watchers.healthy import healthy_watcher
from truepanel.mission_control.watchers.pool import pool_watcher
from truepanel.mission_control.watchers.smart import smart_watcher
from truepanel.mission_control.watchers.storage_health import (
    build_storage_health_watcher,
)
from truepanel.mission_control.watchers.thermal import thermal_watcher
from truepanel.mission_control.watchers.zfs import zfs_watcher
from truepanel.pages.fans import (
    fan_control_page,
    fan_pwm_page,
    fan_rpm_page,
)

LOGGER = logging.getLogger(__name__)

DISPLAY_TIMEOUT = 120
PORT = "/dev/ttyS1"
PORT_SPEED = 1200

lcd = None
lcd_reader_status_bridge = (
    LCDReaderStatusBridge()
)
lcd_display_status_bridge = (
    LCDDisplayStatusBridge()
)
lcd_timer = None
menu_item = 0

zfs_pools = []
ip_addresses = []

collector = TruePanelCollector()
mission = MissionControl()
alert_manager = AlertManager()
config = load_config()
host_bootstrap = build_host_agent_bootstrap(
    config
)
host_agent_runtime = None
storage_health_watcher = build_storage_health_watcher(config)
fan_health_watcher = build_fan_health_watcher(config)
display_manager = DisplayManager(mission, alert_manager, config=config)
autopilot = AutoPilot(display_manager, config=config)
history_recorder = TelemetryRecorder(config.get("history", {}))

buzzer = Buzzer(config.get("buzzer", {}))
bay_led_startup_animation = (
    build_bay_led_startup_animation(
        config
    )
)
shutdown_requested = False

mission.register(pool_watcher)
mission.register(thermal_watcher)
mission.register(zfs_watcher)
mission.register(smart_watcher)

if storage_health_watcher is not None:
    mission.register(storage_health_watcher)

if fan_health_watcher is not None:
    mission.register(fan_health_watcher)

mission.register(healthy_watcher)



def publish_lcd_reader_status():
    """Publish a read-only snapshot of the LCD reader thread."""

    if lcd is None:
        return None

    try:
        return lcd_reader_status_bridge.publish(
            lcd.reader_snapshot()
        )
    except Exception:
        LOGGER.exception(
            "Unable to publish LCD reader status"
        )
        return None


def publish_fan_control_status(
    reason=None,
):
    """Compatibility adapter for Host-owned status publication."""

    if host_agent_runtime is None:
        return host_bootstrap.publish_fan_status(
            reason=reason,
        )

    return host_agent_runtime.publish_fan_status(
        reason=reason,
    )


def observe_thermal_fan_policy(
    telemetry=None,
):
    """
    Evaluate and publish thermal guidance without actuating fan control.

    The automatic_control mode is intentionally unarmed. This observer does
    not request profiles, invoke the command socket, or write fan hardware.
    """

    if host_agent_runtime is None:
        return None

    return host_agent_runtime.observe_thermal(
        telemetry
    )


def end_supervised_thermal_session(
    reason,
    *,
    lifecycle_action,
    telemetry=None,
):
    """Compatibility adapter for Host-owned thermal lifecycle."""

    if host_agent_runtime is None:
        return None

    return host_agent_runtime.end_supervised_thermal_session(
        reason,
        lifecycle_action=lifecycle_action,
        telemetry=telemetry,
    )


def supervised_thermal_session_active():
    if host_agent_runtime is None:
        return False

    return (
        host_agent_runtime
        .supervised_thermal_session_active()
    )


def end_bounded_automatic_lease(
    reason,
    *,
    lifecycle_action,
    telemetry=None,
    restore=True,
):
    """Compatibility adapter for Host-owned thermal lifecycle."""

    if host_agent_runtime is None:
        return None

    return host_agent_runtime.end_bounded_automatic_lease(
        reason,
        lifecycle_action=lifecycle_action,
        telemetry=telemetry,
        restore=restore,
    )


def reconcile_fan_control():
    """Compatibility adapter for Host-owned fan reconciliation."""

    if host_agent_runtime is None:
        return None

    return host_agent_runtime.reconcile_fans()

def lcd_on():
    global lcd_timer

    lcd.backlight(True)

    if lcd_timer:
        lcd_timer.cancel()

    lcd_timer = threading.Timer(
        DISPLAY_TIMEOUT,
        lambda: lcd.backlight(False),
    )
    lcd_timer.daemon = True
    lcd_timer.start()


def shell(cmd):
    return subprocess.check_output(cmd, shell=True, universal_newlines=True).strip()


def refresh_state(force_history=False):
    """
    Refresh collector data and offer the new state to historical telemetry.

    HistoryStore enforces its own sampling interval, so frequent collector
    refreshes do not become frequent disk writes.
    """

    state = collector.update()

    history_recorder.record(
        state,
        alert_count=len(alert_manager.get_history()),
        force=force_history,
    )

    return state


def get_state(max_age=5):
    last = collector.state.get("last_updated")
    now = time.time()

    if last is None or now - last > max_age:
        return refresh_state()

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
        state = refresh_state(force_history=True)
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


def show_fan_control():
    status = (
        host_agent_runtime.read_fan_status(
            max_age=30.0
        )
        if host_agent_runtime is not None
        else None
    )

    lcd.clear()
    lcd.write(
        0,
        fan_control_page(
            status
        ),
    )


def show_fan_pwm():
    lcd.clear()
    lcd.write(0, fan_pwm_page())

def cached_display_state():
    """
    Return the latest collector snapshot without refreshing hardware.

    Physical button navigation must remain responsive even when the normal
    telemetry refresh interval has elapsed. The main loop owns fresh
    collection; button callbacks only render the most recent safe snapshot.
    """

    state = dict(
        collector.state
        or {}
    )

    if state:
        return state

    return get_state()


def publish_lcd_display(
    lines,
    *,
    page=None,
    source="runtime",
):
    try:
        lcd_display_status_bridge.publish(
            lines,
            page=page,
            source=source,
        )
    except Exception:
        LOGGER.exception(
            "Could not publish LCD display status"
        )


def render_lcd_frame(
    lines,
    *,
    page=None,
    source="runtime",
):
    del page, source
    lcd.clear()
    lcd.write(0, lines)


def render_mission_frame(frame):
    """Render one complete Mission Home frame."""

    render_lcd_frame(
        frame.lines,
        page="show_mission_home",
    )


def show_mission_home():
    state = get_state()
    frame = autopilot.tick(state)

    render_mission_frame(frame)


def next_mission_dashboard():
    state = cached_display_state()
    frame = autopilot.next(state)

    render_mission_frame(frame)



def previous_mission_dashboard():
    state = cached_display_state()
    frame = autopilot.previous(state)

    render_mission_frame(frame)



def show_mission_control():
    state = refresh_state()
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
def request_shutdown(signum=None, frame=None):
    global shutdown_requested
    shutdown_requested = True


def maybe_show_alert():
    state = refresh_state()
    frame = display_manager.evaluate(state)

    if frame.interrupt:
        if alert_manager.should_beep(frame.event):
            buzzer.alert(frame.priority)

        show_alert_transition(frame)
        time.sleep(frame.event.timeout)
        return True

    return False


menu = [
    show_mission_home,
    show_truenas,
    show_version,
    show_uptime,
    show_cpu_ram,
    show_pool_health,
    show_zpool,
    show_drive_temps,
    show_fan_rpm,
    show_fan_control,
    show_fan_pwm,
]


def response_handler(command, data):
    global menu_item

    callback_started = time.perf_counter()
    page_name = (
        menu[menu_item].__name__
        if menu
        else "unknown"
    )

    try:
        if command != "Switch_Status":
            return

        # The controller reports zero when a button is released. Release
        # frames must not wake the backlight or trigger another render.
        if not data:
            return

        lcd_on()
        prev_menu = menu_item

        if menu[menu_item] == show_mission_home:
            if data == 0x01:
                previous_mission_dashboard()
                return

            if data == 0x02:
                next_mission_dashboard()
                return

        if data == 0x01:
            menu_item = (menu_item - 1) % len(menu)

        if data == 0x02:
            menu_item = (menu_item + 1) % len(menu)

        if prev_menu != menu_item:
            page_name = menu[
                menu_item
            ].__name__
            menu[menu_item]()

    finally:
        total_ms = (
            time.perf_counter()
            - callback_started
        ) * 1000.0

        if (
            command == "Switch_Status"
            and data
            and total_ms >= 750.0
        ):
            LOGGER.warning(
                (
                    "Abnormal LCD button latency: "
                    "button=0x%04X "
                    "page=%s "
                    "duration_ms=%.3f"
                ),
                data,
                page_name,
                total_ms,
            )



def main():
    global lcd, menu_item
    global host_agent_runtime

    signal.signal(signal.SIGTERM, request_shutdown)
    signal.signal(signal.SIGINT, request_shutdown)

    lcd = qnaplcd.QnapLCD(
        PORT,
        PORT_SPEED,
        response_handler,
    )

    lcd.set_frame_handler(
        lambda lines: publish_lcd_display(
            lines,
            page=(
                menu[menu_item].__name__
                if menu
                else None
            ),
            source="runtime",
        )
    )

    publish_lcd_reader_status()

    lcd_on()
    lcd.reset()
    lcd.clear()

    try:
        host_agent_application_hooks = HostAgentApplicationHooks(
            lcd_button_handler=(
                lambda button_mask, source: (
                    lcd.submit_button_event(
                        button_mask,
                        source=source,
                    )
                )
                if lcd is not None
                else False
            ),
        )

        host_agent_runtime = (
            build_host_agent_runtime_from_bootstrap(
                bootstrap=host_bootstrap,
                application_hooks=(
                    host_agent_application_hooks
                ),
            )
        )

        host_agent_runtime.service_cycle(
            reconcile=False
        )

        host_agent_runtime.start()

        if bay_led_startup_animation is not None:
            bay_led_startup_animation.run()

        show_startup_splash()
        buzzer.startup()
        publish_lcd_reader_status()

        while not shutdown_requested:
            host_agent_runtime.service_cycle()
            publish_lcd_reader_status()
            add_ips_to_menu()

            maybe_show_alert()
            menu[menu_item]()

            delay = 5

            for _ in range(delay * 10):
                if shutdown_requested:
                    break

                time.sleep(0.1)

            if not shutdown_requested:
                menu_item = (
                    menu_item + 1
                ) % len(menu)
    finally:
        if host_agent_runtime is not None:
            try:
                host_agent_runtime.shutdown()
            except Exception:
                pass
            finally:
                host_agent_runtime = None
        else:
            LOGGER.warning(
                "Host Agent runtime was not constructed; "
                "skipping fan-runtime shutdown without ownership."
            )

        try:
            publish_fan_control_status(
                "TruePanel is shutting down; "
                "Automatic restoration requested."
            )
        except Exception:
            pass

        if lcd_timer is not None:
            lcd_timer.cancel()

        publish_lcd_reader_status()

        try:
            buzzer.shutdown()
            write_lines(
                "TruePanel",
                "Shutting Down",
                0.5,
            )
            lcd.backlight(False)
        except Exception:
            pass
        finally:
            try:
                lcd.close()
            except Exception:
                pass
            finally:
                try:
                    publish_lcd_reader_status()
                except Exception:
                    LOGGER.exception(
                        "Failed to publish final LCD reader status"
                    )

main()