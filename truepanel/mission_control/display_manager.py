"""
Display Manager

Coordinates Mission Control events, Alert Manager decisions,
registry-driven dashboard pages, event queue pages, alert history,
and LCD-safe graphical rendering.

It does not communicate directly with LCD hardware.
"""

from dataclasses import dataclass
import inspect
from typing import Optional

from .constants import Priority
from .event import MissionEvent
from .renderer import render_event

from truepanel.display import Canvas, sanitize
from truepanel.themes import Theme
from truepanel.display.widgets import (
    activity_meter,
    dual_meter,
    labeled_bar,
    progress_bar,
    sparkline,
    status_icon,
)


from truepanel.lab.widgets.render import (
    renderer as widget_renderer,
)


LCD_WIDTH = 16


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
        return [
            sanitize(self.line1, width=LCD_WIDTH, pad=True),
            sanitize(self.line2, width=LCD_WIDTH, pad=True),
        ]


class DisplayManager:
    def __init__(
        self,
        mission,
        alert_manager,
        config=None,
        registry=None,
    ):
        self.mission = mission
        self.alert_manager = alert_manager
        self.config = config or {}
        self.theme = self.config.get("theme", {})
        self.theme_engine = Theme(self.config)

        self.registry = registry or self.config.get("registry")

        if self.registry is None:
            # Load plugins only when a registry was not supplied.
            # Importing here avoids the plugins/collectors circular import.
            from truepanel.plugins import load_plugins

            self.registry = load_plugins(self.config)

        self.mode = DisplayMode.NORMAL
        self.history_index = 0
        self.queue_index = 0
        self.dashboard_index = 0

        self.performance_history = []
        self.activity_history = []
        self.alert_flash_frame = 0

        self.builtin_dashboard_pages = {
            "home": self._dashboard_home,
            "storage": self._dashboard_storage,
            "capacity": self._dashboard_capacity,
            "performance": self._dashboard_performance,
            "thermal": self._dashboard_thermal,
            "smart": self._dashboard_smart,
            "activity": self._dashboard_activity,
            "network": self._dashboard_network,
        }

        self.dashboard_pages = self.build_dashboard_pages()

    def build_dashboard_pages(self):
        pages = []

        for page in getattr(self.registry, "dashboard_pages", []):
            renderer = page.get("renderer")

            if renderer is None:
                renderer = self.builtin_dashboard_pages.get(page.get("id"))

            if renderer is not None:
                pages.append(
                    {
                        "id": page.get("id", "unknown"),
                        "title": page.get(
                            "title",
                            page.get("id", "Dashboard"),
                        ),
                        "renderer": renderer,
                    }
                )

        if not pages:
            default_order = [
                "home",
                "performance",
                "storage",
                "capacity",
                "activity",
                "thermal",
                "smart",
                "network",
            ]

            for page_id in default_order:
                renderer = self.builtin_dashboard_pages.get(page_id)

                if renderer:
                    pages.append(
                        {
                            "id": page_id,
                            "title": page_id.title(),
                            "renderer": renderer,
                        }
                    )

        return pages

    def dashboard_count(self):
        return len(self.dashboard_pages)

    def dashboard_page_ids(self):
        return [page["id"] for page in self.dashboard_pages]

    def make_frame(
        self,
        line1,
        line2,
        priority=Priority.INFO,
        timeout=5,
        interrupt=False,
        event=None,
        mode=DisplayMode.DASHBOARD,
    ):
        return DisplayFrame(
            mode=mode,
            line1=sanitize(line1, width=LCD_WIDTH),
            line2=sanitize(line2, width=LCD_WIDTH),
            priority=priority,
            timeout=timeout,
            interrupt=interrupt,
            event=event,
        )

    def canvas_frame(
        self,
        canvas,
        priority=Priority.INFO,
        timeout=5,
        interrupt=False,
        event=None,
        mode=DisplayMode.DASHBOARD,
    ):
        lines = canvas.render()

        return self.make_frame(
            line1=lines[0] if lines else "",
            line2=lines[1] if len(lines) > 1 else "",
            priority=priority,
            timeout=timeout,
            interrupt=interrupt,
            event=event,
            mode=mode,
        )

    def theme_value(self, key, default):
        return self.theme.get(key, default)

    def status_prefix(self, priority):
        return self.theme_engine.status(priority)

    def mission_title(self, state, priority):
        hostname = state.get("hostname", "BattleStation")
        return f"{self.status_prefix(priority)} {hostname}"[:LCD_WIDTH]

    @staticmethod
    def numeric(value, default=0.0):
        try:
            return float(value)
        except (TypeError, ValueError):
            return float(default)

    @staticmethod
    def integer(value, default=0):
        try:
            return int(round(float(value)))
        except (TypeError, ValueError):
            return int(default)

    @staticmethod
    def rate_text(value):
        value = DisplayManager.numeric(value)

        if value >= 1024 * 1024 * 1024:
            return f"{value / (1024 ** 3):.1f}G"

        if value >= 1024 * 1024:
            return f"{value / (1024 ** 2):.1f}M"

        if value >= 1024:
            return f"{value / 1024:.0f}K"

        return f"{value:.0f}B"

    def evaluate(self, state):
        event = self.mission.evaluate(state)
        decision = self.alert_manager.evaluate(event)

        if decision.interrupt:
            return self.render_alert_detail(event)

        rendered = render_event(event)

        return self.make_frame(
            mode=DisplayMode.NORMAL,
            line1=rendered[0],
            line2=rendered[1],
            priority=event.priority,
            timeout=event.timeout,
            interrupt=False,
            event=event,
        )

    def render_alert_detail(self, event):
        self.alert_flash_frame += 1

        if event.event_id in ("storage.scrub", "storage.resilver"):
            try:
                percent = int(str(event.message).strip("%"))

                canvas = Canvas()
                canvas.text(
                    0,
                    0,
                    f"{status_icon(event.priority)} {event.title}",
                )
                canvas.text(
                    0,
                    1,
                    self.theme_engine.bar(percent, width=LCD_WIDTH),
                )

                return self.canvas_frame(
                    canvas,
                    priority=event.priority,
                    timeout=event.timeout,
                    interrupt=True,
                    event=event,
                    mode=DisplayMode.ALERT,
                )
            except (TypeError, ValueError):
                pass

        canvas = Canvas()

        if event.priority >= Priority.CRITICAL:
            label = self.theme_engine.text("alert_banner", "SYSTEM ALERT")
            banner = f"{self.theme_engine.status(event.priority)} {label}"
        elif event.priority >= Priority.WARNING:
            label = self.theme_engine.text("warning_banner", "WARNING")
            banner = f"{self.theme_engine.status(event.priority)} {label}"
        else:
            banner = "SYSTEM NOTICE"

        canvas.text(0, 0, banner, width=LCD_WIDTH, align="center")
        canvas.text(0, 1, event.title, width=LCD_WIDTH, align="center")

        return self.canvas_frame(
            canvas,
            priority=event.priority,
            timeout=event.timeout,
            interrupt=True,
            event=event,
            mode=DisplayMode.ALERT,
        )

    def invoke_renderer(self, renderer, state):
        """
        Invoke built-in and plugin dashboard renderers.

        Built-in bound methods accept ``state``.
        Plugin renderers may accept ``state, display_manager``.
        """

        try:
            signature = inspect.signature(renderer)
            positional = [
                parameter
                for parameter in signature.parameters.values()
                if parameter.kind
                in (
                    inspect.Parameter.POSITIONAL_ONLY,
                    inspect.Parameter.POSITIONAL_OR_KEYWORD,
                )
            ]
        except (TypeError, ValueError):
            positional = []

        if len(positional) >= 2:
            return renderer(state, self)

        return renderer(state)

    def render_dashboard(self, state):
        if self.dashboard_index >= self.dashboard_count():
            self.dashboard_index = 0

        page = self.dashboard_pages[self.dashboard_index]
        renderer = page["renderer"]

        return self.invoke_renderer(renderer, state)

    def next_dashboard(self, state):
        self.dashboard_index = (
            self.dashboard_index + 1
        ) % self.dashboard_count()

        return self.render_dashboard(state)

    def _dashboard_home(self, state):
        event = self.mission.evaluate(state)
        history = self.alert_manager.get_history()
        alert_count = len(history)

        canvas = Canvas()

        if event.priority >= Priority.WARNING:
            priority = event.priority
            event_obj = event

            canvas.text(
                0,
                0,
                f"{status_icon(priority)} MISSION ALERT",
                width=LCD_WIDTH,
            )
            canvas.text(
                0,
                1,
                event.title,
                width=LCD_WIDTH,
                align="center",
            )

        elif alert_count:
            priority = Priority.WARNING
            event_obj = history[0]

            canvas.text(
                0,
                0,
                f"{self.theme_engine.status(Priority.WARNING)} "
                f"{self.theme_engine.text('system_watch', 'SYSTEM WATCH')}",
                width=LCD_WIDTH,
            )
            canvas.text(
                0,
                1,
                f"{alert_count} Stored Alert"
                + ("s" if alert_count != 1 else ""),
                width=LCD_WIDTH,
                align="center",
            )

        else:
            priority = Priority.HEALTHY
            event_obj = event

            canvas.text(
                0,
                0,
                f"{self.theme_engine.status(Priority.HEALTHY)} "
                f"{self.theme_engine.text('mission_ready', 'MISSION READY')}",
                width=LCD_WIDTH,
                align="center",
            )
            canvas.text(
                0,
                1,
                self.theme_engine.text("all_systems_go", "All Systems GO"),
                width=LCD_WIDTH,
                align="center",
            )

        return self.canvas_frame(
            canvas,
            priority=priority,
            timeout=5,
            interrupt=False,
            event=event_obj,
        )

    def _dashboard_storage(self, state):
        pools = state.get("pools", [])

        canvas = Canvas()

        if not pools:
            canvas.text(0, 0, "STORAGE STATUS")
            canvas.text(0, 1, "No Pool Data")
            return self.canvas_frame(canvas)

        bad = [
            pool
            for pool in pools
            if str(pool.get("health", "")).upper() != "ONLINE"
        ]

        if bad:
            pool = bad[0]
            name = pool.get("name", "pool")
            health = pool.get("health", "UNKNOWN")

            canvas.text(0, 0, "X POOL ALERT X")
            canvas.text(
                0,
                1,
                f"{name[:8]} {health[:7]}",
            )

            priority = Priority.CRITICAL
        else:
            canvas.text(
                0,
                0,
                f"{self.theme_engine.status(Priority.HEALTHY)} "
                f"{self.theme_engine.text('pool_healthy', 'POOLS ONLINE')}",
                width=LCD_WIDTH,
                align="center",
            )
            canvas.text(
                0,
                1,
                f"{len(pools)} Pool"
                + ("s" if len(pools) != 1 else "")
                + " Healthy",
                width=LCD_WIDTH,
                align="center",
            )

            priority = Priority.HEALTHY

        return self.canvas_frame(
            canvas,
            priority=priority,
        )

    def _dashboard_capacity(self, state):
        pools = state.get("pools", [])

        if not pools:
            return self.make_frame(
                "CAPACITY",
                "No Pool Data",
                Priority.INFO,
            )

        def pool_pct(pool):
            capacity = pool.get("capacity", 0)

            try:
                return int(str(capacity).strip("%"))
            except (TypeError, ValueError):
                return 0

        fullest = max(pools, key=pool_pct)
        name = str(fullest.get("name", "pool"))
        percent = pool_pct(fullest)

        canvas = Canvas()
        canvas.text(
            0,
            0,
            f"{name[:9]} {percent:>3}%",
        )
        canvas.text(
            0,
            1,
            self.theme_engine.bar(percent, width=LCD_WIDTH),
        )

        if percent >= 95:
            priority = Priority.CRITICAL
        elif percent >= 85:
            priority = Priority.WARNING
        else:
            priority = Priority.INFO

        return self.canvas_frame(
            canvas,
            priority=priority,
        )

    def _dashboard_performance(self, state):
        cpu = self.integer(state.get("cpu_percent", 0))
        ram = self.integer(state.get("ram_percent", 0))

        self.performance_history.append(max(cpu, ram))
        self.performance_history = self.performance_history[-16:]

        line1, line2 = widget_renderer.performance_lines(
            cpu,
            ram,
        )

        canvas = Canvas()
        canvas.text(0, 0, line1)
        canvas.text(0, 1, line2)

        priority = (
            Priority.WARNING
            if cpu >= 90 or ram >= 90
            else Priority.INFO
        )

        return self.canvas_frame(
            canvas,
            priority=priority,
        )

    def _dashboard_thermal(self, state):
        temps = state.get("temps", [])

        if not temps:
            return self.make_frame(
                "THERMAL",
                "No Temp Data",
                Priority.INFO,
            )

        hottest = max(
            temps,
            key=lambda drive: self.numeric(drive.get("temp", 0)),
        )

        drive = str(hottest.get("drive", "disk"))
        temp = self.integer(hottest.get("temp", 0))

        gauge_percent = min(100, max(0, temp * 2))

        canvas = Canvas()
        canvas.text(
            0,
            0,
            f"TEMP {drive[:5]:<5} {temp:>2}C",
        )
        canvas.text(
            0,
            1,
            self.theme_engine.bar(gauge_percent, width=LCD_WIDTH),
        )

        if temp >= 60:
            priority = Priority.CRITICAL
        elif temp >= 50:
            priority = Priority.WARNING
        else:
            priority = Priority.HEALTHY

        return self.canvas_frame(
            canvas,
            priority=priority,
        )

    def _dashboard_smart(self, state):
        smart = state.get("smart", [])

        if not smart:
            return self.make_frame(
                "SMART STATUS",
                "No SMART Data",
                Priority.INFO,
            )

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
            elif drive.get(
                "critical_warning",
                "0x00",
            ) not in ["0x00", "0"]:
                problem_drives.append(drive)

        canvas = Canvas()

        if problem_drives:
            drive = problem_drives[0]
            drive_name = drive.get(
                "drive",
                drive.get("device", "disk"),
            )

            canvas.text(
                0,
                0,
                "X SMART ALERT X",
                width=LCD_WIDTH,
                align="center",
            )
            canvas.text(
                0,
                1,
                str(drive_name),
                width=LCD_WIDTH,
                align="center",
            )

            priority = Priority.CRITICAL
        else:
            canvas.text(
                0,
                0,
                "O SMART HEALTHY",
                width=LCD_WIDTH,
                align="center",
            )
            canvas.text(
                0,
                1,
                f"{len(smart)} Drives Checked",
                width=LCD_WIDTH,
                align="center",
            )

            priority = Priority.HEALTHY

        return self.canvas_frame(
            canvas,
            priority=priority,
        )

    def _dashboard_activity(self, state):
        activity = state.get("zfs_activity", {}) or {}

        read_rate = self.numeric(
            activity.get(
                "read_bytes_per_sec",
                activity.get("read_rate", 0),
            )
        )
        write_rate = self.numeric(
            activity.get(
                "write_bytes_per_sec",
                activity.get("write_rate", 0),
            )
        )

        total = read_rate + write_rate
        self.activity_history.append(total)
        self.activity_history = self.activity_history[-16:]

        maximum = max(self.activity_history or [1])
        activity_percent = (
            0 if maximum <= 0 else (total / maximum) * 100
        )

        canvas = Canvas()

        if total <= 0:
            canvas.text(
                0,
                0,
                "ZFS POOL IDLE",
                width=LCD_WIDTH,
                align="center",
            )
            canvas.text(0, 1, "." * LCD_WIDTH)
        else:
            canvas.text(
                0,
                0,
                f"R{self.rate_text(read_rate):>6} "
                f"W{self.rate_text(write_rate):>6}",
            )
            canvas.text(
                0,
                1,
                activity_meter(
                    activity_percent,
                    maximum=100,
                    width=LCD_WIDTH,
                ),
            )

        return self.canvas_frame(
            canvas,
            priority=Priority.INFO,
        )

    def _dashboard_network(self, state):
        network = state.get("network", {}) or {}

        upload = self.numeric(
            network.get(
                "upload_bytes_per_sec",
                network.get(
                    "tx_bytes_per_sec",
                    network.get("tx_rate", 0),
                ),
            )
        )

        download = self.numeric(
            network.get(
                "download_bytes_per_sec",
                network.get(
                    "rx_bytes_per_sec",
                    network.get("rx_rate", 0),
                ),
            )
        )

        ip_address = (
            network.get("ip")
            or network.get("address")
            or state.get("ip_address")
            or state.get("ip")
            or "No Address"
        )

        canvas = Canvas()
        canvas.text(
            0,
            0,
            f"^{self.rate_text(upload):<6} "
            f"v{self.rate_text(download):<6}",
        )
        canvas.text(
            0,
            1,
            str(ip_address),
            width=LCD_WIDTH,
            align="center",
        )

        return self.canvas_frame(
            canvas,
            priority=Priority.INFO,
        )

    def render_history(self):
        history = self.alert_manager.get_history()

        if not history:
            return self.make_frame(
                "ALERT HISTORY",
                "No Alerts",
                Priority.HEALTHY,
                mode=DisplayMode.HISTORY,
            )

        if self.history_index >= len(history):
            self.history_index = 0

        event = history[self.history_index]

        return self.make_frame(
            line1=f"ALERT {self.history_index + 1}/{len(history)}",
            line2=f"{status_icon(event.priority)} {event.title}",
            priority=event.priority,
            timeout=5,
            interrupt=False,
            event=event,
            mode=DisplayMode.HISTORY,
        )

    def next_history(self):
        history = self.alert_manager.get_history()

        if history:
            self.history_index = (
                self.history_index + 1
            ) % len(history)
        else:
            self.history_index = 0

        return self.render_history()

    def render_event_queue(self):
        history = self.alert_manager.get_history()

        if not history:
            return self.make_frame(
                "O SYSTEM QUIET",
                "Queue Empty",
                Priority.HEALTHY,
                mode=DisplayMode.QUEUE,
            )

        if self.queue_index >= len(history):
            self.queue_index = 0

        event = history[self.queue_index]

        return self.make_frame(
            line1=f"QUEUE {self.queue_index + 1}/{len(history)}",
            line2=f"{status_icon(event.priority)} {event.title}",
            priority=event.priority,
            timeout=5,
            interrupt=False,
            event=event,
            mode=DisplayMode.QUEUE,
        )

    def next_event_queue(self):
        history = self.alert_manager.get_history()

        if history:
            self.queue_index = (
                self.queue_index + 1
            ) % len(history)
        else:
            self.queue_index = 0

        return self.render_event_queue()
