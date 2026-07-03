"""
Display Manager

Coordinates Mission Control events, Alert Manager decisions, dashboard pages,
event queue pages, alert history, and LCD-safe rendering.

It does not talk directly to LCD hardware.
"""

from dataclasses import dataclass
from typing import Optional

from .constants import Priority
from .event import MissionEvent
from .renderer import render_event
from truepanel.display.widgets import progress_bar


class DisplayMode:
    NORMAL = "normal"
    ALERT = "alert"
    HISTORY = "history"
    QUEUE = "queue"
    DASHBOARD = "dashboard"


@dataclass
class DisplayFrame:
    mode: str
    line1: str
    line2: str
    priority: Priority
    timeout: int
    interrupt: bool
    event: Optional[MissionEvent] = None

    @property
    def lines(self):
        return [self.line1[:16], self.line2[:16]]


class DisplayManager:
    def __init__(self, mission, alert_manager):
        self.mission = mission
        self.alert_manager = alert_manager
        self.mode = DisplayMode.NORMAL
        self.history_index = 0
        self.queue_index = 0
        self.dashboard_index = 0

    def evaluate(self, state):
        event = self.mission.evaluate(state)
        decision = self.alert_manager.evaluate(event)

        if decision.interrupt:
            self.mode = DisplayMode.ALERT
            return DisplayFrame(
                mode=self.mode,
                line1="*** ALERT ***",
                line2=event.title,
                priority=event.priority,
                timeout=2,
                interrupt=True,
                event=event,
            )

        rendered = render_event(event)
        return DisplayFrame(
            mode=DisplayMode.NORMAL,
            line1=rendered[0],
            line2=rendered[1],
            priority=event.priority,
            timeout=event.timeout,
            interrupt=False,
            event=event,
        )

    def render_alert_detail(self, event):
        if event.event_id in ("storage.scrub", "storage.resilver"):
            try:
                percent = int(str(event.message).strip("%"))
                return DisplayFrame(
                    mode=DisplayMode.ALERT,
                    line1=f"{event.title} {percent}%",
                    line2=progress_bar(percent),
                    priority=event.priority,
                    timeout=event.timeout,
                    interrupt=True,
                    event=event,
                )
            except Exception:
                pass

        rendered = render_event(event)
        return DisplayFrame(
            mode=DisplayMode.ALERT,
            line1=rendered[0],
            line2=rendered[1],
            priority=event.priority,
            timeout=event.timeout,
            interrupt=True,
            event=event,
        )

    def render_dashboard(self, state):
        pages = [
            self._dashboard_home,
            self._dashboard_storage,
            self._dashboard_capacity,
            self._dashboard_performance,
            self._dashboard_thermal,
            self._dashboard_smart,
        ]

        if self.dashboard_index >= len(pages):
            self.dashboard_index = 0

        return pages[self.dashboard_index](state)

    def next_dashboard(self, state):
        self.dashboard_index = (self.dashboard_index + 1) % 6
        return self.render_dashboard(state)

    def _dashboard_home(self, state):
        event = self.mission.evaluate(state)
        history = self.alert_manager.get_history()
        alert_count = len(history)

        if event.priority >= Priority.WARNING:
            line2 = event.title
            priority = event.priority
            event_obj = event
        elif alert_count:
            line2 = f"{alert_count} Alert" + ("s" if alert_count != 1 else "")
            priority = Priority.WARNING
            event_obj = history[0]
        else:
            line2 = "Healthy"
            priority = Priority.HEALTHY
            event_obj = event

        return DisplayFrame(
            mode=DisplayMode.DASHBOARD,
            line1=state.get("hostname", "BattleStation"),
            line2=line2,
            priority=priority,
            timeout=5,
            interrupt=False,
            event=event_obj,
        )

    def _dashboard_storage(self, state):
        pools = state.get("pools", [])

        if not pools:
            line2 = "No Pool Data"
            priority = Priority.INFO
        else:
            bad = [pool for pool in pools if pool.get("health") != "ONLINE"]

            if bad:
                line2 = f"{len(bad)} Pool Alert" + ("s" if len(bad) != 1 else "")
                priority = Priority.CRITICAL
            else:
                line2 = f"{len(pools)} Pools OK"
                priority = Priority.HEALTHY

        return DisplayFrame(
            mode=DisplayMode.DASHBOARD,
            line1="Storage",
            line2=line2,
            priority=priority,
            timeout=5,
            interrupt=False,
        )

    def _dashboard_capacity(self, state):
        pools = state.get("pools", [])

        if not pools:
            return DisplayFrame(
                mode=DisplayMode.DASHBOARD,
                line1="Capacity",
                line2="No Pool Data",
                priority=Priority.INFO,
                timeout=5,
                interrupt=False,
            )

        fullest = max(
            pools,
            key=lambda pool: int(str(pool.get("capacity", "0%")).strip("%") or 0),
        )

        name = fullest.get("name", "pool")
        capacity = fullest.get("capacity", "0%")

        try:
            pct = int(str(capacity).strip("%"))
        except Exception:
            pct = 0

        return DisplayFrame(
            mode=DisplayMode.DASHBOARD,
            line1=f"{name[:9]} {pct}%",
            line2=progress_bar(pct),
            priority=Priority.WARNING if pct >= 85 else Priority.INFO,
            timeout=5,
            interrupt=False,
        )

    def _dashboard_performance(self, state):
        cpu = state.get("cpu_percent", 0)
        ram = state.get("ram_percent", 0)

        return DisplayFrame(
            mode=DisplayMode.DASHBOARD,
            line1=f"CPU {cpu}% RAM {ram}%",
            line2=progress_bar(max(cpu, ram)),
            priority=Priority.WARNING if cpu >= 90 or ram >= 90 else Priority.INFO,
            timeout=5,
            interrupt=False,
        )

    def _dashboard_thermal(self, state):
        temps = state.get("temps", [])

        if not temps:
            line2 = "No Temp Data"
            priority = Priority.INFO
        else:
            hottest = max(temps, key=lambda drive: drive.get("temp", 0))
            drive = hottest.get("drive", "disk")
            temp = hottest.get("temp", 0)
            line2 = f"{drive} {temp}C"
            priority = Priority.WARNING if temp >= 50 else Priority.HEALTHY

        return DisplayFrame(
            mode=DisplayMode.DASHBOARD,
            line1="Thermal",
            line2=line2,
            priority=priority,
            timeout=5,
            interrupt=False,
        )

    def _dashboard_smart(self, state):
        smart = state.get("smart", [])

        if not smart:
            line2 = "No SMART Data"
            priority = Priority.INFO
        else:
            problem_drives = []

            for drive in smart:
                if drive.get("health") == "FAILED":
                    problem_drives.append(drive)
                elif drive.get("pending", 0) > 0:
                    problem_drives.append(drive)
                elif drive.get("offline_uncorrectable", 0) > 0:
                    problem_drives.append(drive)
                elif drive.get("media_errors", 0) > 0:
                    problem_drives.append(drive)
                elif drive.get("critical_warning", "0x00") not in ["0x00", "0"]:
                    problem_drives.append(drive)

            if problem_drives:
                line2 = f"{len(problem_drives)} SMART Alert"
                if len(problem_drives) != 1:
                    line2 += "s"
                priority = Priority.CRITICAL
            else:
                line2 = f"{len(smart)} Drives OK"
                priority = Priority.HEALTHY

        return DisplayFrame(
            mode=DisplayMode.DASHBOARD,
            line1="SMART",
            line2=line2,
            priority=priority,
            timeout=5,
            interrupt=False,
        )

    def render_history(self):
        history = self.alert_manager.get_history()

        if not history:
            return DisplayFrame(DisplayMode.HISTORY, "Alert History", "No Alerts", Priority.INFO, 5, False)

        if self.history_index >= len(history):
            self.history_index = 0

        event = history[self.history_index]
        return DisplayFrame(DisplayMode.HISTORY, f"Alert {self.history_index + 1}/{len(history)}", event.title, event.priority, 5, False, event)

    def next_history(self):
        history = self.alert_manager.get_history()
        self.history_index = 0 if not history else (self.history_index + 1) % len(history)
        return self.render_history()

    def render_event_queue(self):
        history = self.alert_manager.get_history()

        if not history:
            return DisplayFrame(DisplayMode.QUEUE, "No Alerts", "System Quiet", Priority.HEALTHY, 5, False)

        if self.queue_index >= len(history):
            self.queue_index = 0

        event = history[self.queue_index]
        return DisplayFrame(DisplayMode.QUEUE, f"Queue {self.queue_index + 1}/{len(history)}", event.title, event.priority, 5, False, event)

    def next_event_queue(self):
        history = self.alert_manager.get_history()
        self.queue_index = 0 if not history else (self.queue_index + 1) % len(history)
        return self.render_event_queue()
