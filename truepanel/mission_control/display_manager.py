"""
Display Manager

Coordinates Mission Control events, Alert Manager decisions,
registry-driven dashboard pages, event queue pages, alert history,
and LCD-safe graphical rendering.

It does not communicate directly with LCD hardware.
"""

from dataclasses import dataclass
from pathlib import Path
import ipaddress
import json
import socket
import subprocess
import inspect
from typing import Optional

from .constants import Category, Priority
from .event import MissionEvent
from .renderer import render_event
from .storage_alerts import render_storage_alert

from truepanel.display import (
    Canvas,
    NativeInstrumentRenderer,
    sanitize,
)
from truepanel.display.instruments import (
    CapacityWidget,
    InstrumentPage,
    PerformanceTrendWidget,
    PerformanceWidget,
    ThermalWidget,
)
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
        self.native_renderer = NativeInstrumentRenderer(
    raw_blocks=False
)

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

        self.cpu_history = []
        self.ram_history = []
        self.activity_history = []
        self.network_history = []
        self.network_interface_index = 0
        self.alert_flash_frame = 0
        self.latest_storage_event = None

        self.builtin_dashboard_pages = {
            "home": self._dashboard_home,
            "storage": self._dashboard_storage,
            "capacity": self._dashboard_capacity,
            "performance": self._dashboard_performance,
            "thermal": self._dashboard_thermal,
            "smart": self._dashboard_smart,
            "activity": self._dashboard_activity,
            "network": self._dashboard_network,
            "tailscale": self._dashboard_tailscale,
        }

        self.dashboard_pages = self.build_dashboard_pages()

    def build_dashboard_pages(self):
        pages = []

        for page in getattr(self.registry, "dashboard_pages", []):
            renderer = page.get("renderer")

            if renderer is None:
                renderer = self.builtin_dashboard_pages.get(page.get("id"))

            if renderer is not None:
                page_id = page.get("id", "unknown")

                pages.append(
                    {
                        "id": page_id,
                        "title": page.get(
                            "title",
                            page_id,
                        ),
                        "renderer": renderer,
                    }
                )

                # The built-in network dashboard is intentionally split
                # into local and Tailscale identity pages so that full
                # addresses fit comfortably on the 16-character LCD.
                if (
                    page_id == "network"
                    and renderer == self._dashboard_network
                ):
                    pages.append(
                        {
                            "id": "tailscale",
                            "title": "Tailscale",
                            "renderer": self._dashboard_tailscale,
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
                "tailscale",
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

    @staticmethod
    def center_text(text):
        """Center a label within the LCD width."""
        return str(text)[:LCD_WIDTH].center(LCD_WIDTH)

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

    def instrument_frame(
        self,
        page,
        priority=Priority.INFO,
        timeout=5,
        interrupt=False,
        event=None,
        mode=DisplayMode.DASHBOARD,
    ):
        """
        Render an InstrumentPage through the standard DisplayFrame pipeline.

        Instrument pages produce exact-width native byte rows. DisplayManager
        decodes those rows through Latin-1 so every byte survives unchanged
        until the hardware-writing boundary.
        """

        if not isinstance(page, InstrumentPage):
            raise TypeError(
                "instrument_frame requires an InstrumentPage"
            )

        instrument = page.render()

        return self.make_frame(
            line1=instrument.line1.decode("latin-1"),
            line2=instrument.line2.decode("latin-1"),
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

        self._track_storage_event(event)

        if (
            decision.interrupt
            and not self._is_bay_storage_event(event)
        ):
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

    @staticmethod
    def _event_metadata(event):
        metadata = getattr(event, "metadata", {})

        if isinstance(metadata, dict):
            return metadata

        return {}

    @classmethod
    def _is_bay_storage_event(cls, event):
        if event.category != Category.STORAGE:
            return False

        metadata = cls._event_metadata(event)

        try:
            bay = int(metadata.get("physical_bay"))
        except (TypeError, ValueError):
            return False

        return (
            1 <= bay <= 6
            and bool(metadata.get("change_type"))
        )

    def _track_storage_event(self, event):
        if not self._is_bay_storage_event(event):
            return

        metadata = self._event_metadata(event)

        change_type = str(
            metadata.get("change_type", "")
        ).strip().lower()

        new_state = str(
            metadata.get("new_state", "")
        ).strip().lower()

        if (
            change_type in {
                "recovered",
                "device_inserted",
            }
            or new_state == "healthy"
        ):
            self.latest_storage_event = None
            return

        if event.priority >= Priority.WARNING:
            self.latest_storage_event = event

    def render_alert_detail(self, event):
        self.alert_flash_frame += 1

        if event.event_id in ("storage.scrub", "storage.resilver"):
            metadata = getattr(event, "metadata", {})
            percent = metadata.get("percent")

            if percent is None:
                try:
                    percent = int(str(event.message).strip("%"))
                except (TypeError, ValueError):
                    percent = None

            if percent is not None:
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

        storage_alert = render_storage_alert(event)

        if storage_alert is not None:
            return self.make_frame(
                line1=storage_alert.line1,
                line2=storage_alert.line2,
                priority=event.priority,
                timeout=event.timeout,
                interrupt=True,
                event=event,
                mode=DisplayMode.ALERT,
            )

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
                "MISSION ALERT",
                width=LCD_WIDTH,
                align="center",
            )
            canvas.text(
                0,
                1,
                widget_renderer.performance_bar_line(
                    "ALT",
                    100,
                ),
            )

        elif alert_count:
            priority = Priority.WARNING
            event_obj = history[0]

            watch_percent = min(
                100,
                max(1, alert_count) * 20,
            )

            canvas.text(
                0,
                0,
                self.theme_engine.text(
                    "system_watch",
                    "SYSTEM WATCH",
                ),
                width=LCD_WIDTH,
                align="center",
            )
            canvas.text(
                0,
                1,
                widget_renderer.performance_bar_line(
                    "ALT",
                    watch_percent,
                ),
            )

        else:
            priority = Priority.HEALTHY
            event_obj = event

            canvas.text(
                0,
                0,
                self.theme_engine.text(
                    "mission_ready",
                    "MISSION READY",
                ),
                width=LCD_WIDTH,
                align="center",
            )
            canvas.text(
                0,
                1,
                widget_renderer.performance_bar_line(
                    "SYS",
                    100,
                ),
            )

        return self.canvas_frame(
            canvas,
            priority=priority,
            timeout=5,
            interrupt=False,
            event=event_obj,
        )

    def _dashboard_storage(self, state):
        if self.latest_storage_event is not None:
            content = render_storage_alert(
                self.latest_storage_event
            )

            if content is not None:
                return self.make_frame(
                    line1=content.line1,
                    line2=content.line2,
                    priority=(
                        self.latest_storage_event.priority
                    ),
                    timeout=5,
                    interrupt=False,
                    event=self.latest_storage_event,
                    mode=DisplayMode.DASHBOARD,
                )

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

    @staticmethod
    def _dashboard_indicator(priority):
        """Return a compact ASCII health indicator for the LCD."""
        if priority == Priority.CRITICAL:
            return "X"

        if priority == Priority.WARNING:
            return "!"

        if priority == Priority.HEALTHY:
            return "O"

        return ""

    def dashboard_frame(
        self,
        title,
        value,
        priority=Priority.INFO,
        indicator=None,
    ):
        """
        Build a consistent two-line text dashboard frame.

        Titles are centered. Data remains left-aligned. When present, the
        final character of line one is reserved for a health indicator.
        """
        if indicator is None:
            indicator = self._dashboard_indicator(priority)

        title = str(title)
        value = str(value)

        if indicator:
            title_width = LCD_WIDTH - 2
            line1 = (
                title[:title_width].center(title_width)
                + " "
                + str(indicator)[:1]
            )
        else:
            line1 = self.center_text(title)

        return self.make_frame(
            line1,
            value,
            priority=priority,
        )

    def dashboard_pair(
        self,
        title,
        left,
        right,
        priority=Priority.INFO,
        indicator=None,
    ):
        """Build a dashboard frame containing two compact data values."""
        value = f"{left}  {right}"

        return self.dashboard_frame(
            title,
            value,
            priority=priority,
            indicator=indicator,
        )

    @staticmethod
    def compact_rate(rate):
        """Format a byte rate for a narrow LCD data line."""
        try:
            value = max(0.0, float(rate))
        except (TypeError, ValueError):
            value = 0.0

        units = (
            (1024 ** 3, "G"),
            (1024 ** 2, "M"),
            (1024, "K"),
        )

        for divisor, suffix in units:
            if value >= divisor:
                scaled = value / divisor

                if scaled >= 10:
                    return f"{scaled:.0f}{suffix}"

                return f"{scaled:.1f}{suffix}"

        return f"{value:.0f}B"

    def _dashboard_capacity(self, state):
        pools = state.get("pools", [])

        if not pools:
            return self.dashboard_frame(
                "Storage",
                "No Pool Data",
                Priority.INFO,
            )

        def pool_pct(pool):
            capacity = pool.get("capacity", 0)

            try:
                return max(
                    0,
                    min(
                        100,
                        int(
                            str(capacity).strip("%")
                        ),
                    ),
                )
            except (TypeError, ValueError):
                return 0

        fullest = max(
            pools,
            key=pool_pct,
        )
        percent = pool_pct(fullest)

        if percent >= 95:
            priority = Priority.CRITICAL
        elif percent >= 85:
            priority = Priority.WARNING
        else:
            priority = Priority.INFO

        return self.dashboard_frame(
            "Storage",
            f"{percent}% Used",
            priority=priority,
        )

    def _dashboard_performance(self, state):
        cpu = max(
            0,
            min(
                100,
                self.integer(
                    state.get("cpu_percent", 0)
                ),
            ),
        )
        ram = max(
            0,
            min(
                100,
                self.integer(
                    state.get("ram_percent", 0)
                ),
            ),
        )

        # Preserve whichever history model is present.
        if hasattr(self, "cpu_history"):
            self.cpu_history.append(cpu)
            self.cpu_history = self.cpu_history[-16:]

        if hasattr(self, "ram_history"):
            self.ram_history.append(ram)
            self.ram_history = self.ram_history[-16:]

        if hasattr(self, "performance_history"):
            self.performance_history.append(
                max(cpu, ram)
            )
            self.performance_history = (
                self.performance_history[-16:]
            )

        priority = (
            Priority.WARNING
            if cpu >= 90 or ram >= 90
            else Priority.INFO
        )

        return self.dashboard_pair(
            "CPU / Memory",
            f"CPU {cpu}%",
            f"RAM {ram}%",
            priority=priority,
        )

    def _dashboard_thermal(self, state):
        temps = state.get("temps", [])

        if not temps:
            return self.dashboard_frame(
                "Drive Temp",
                "No Temp Data",
                Priority.INFO,
            )

        hottest = max(
            temps,
            key=lambda drive: self.numeric(
                drive.get("temp", 0)
            ),
        )

        drive = str(
            hottest.get(
                "drive",
                hottest.get("device", "disk"),
            )
        )
        temp = self.integer(
            hottest.get("temp", 0)
        )

        if temp >= 60:
            priority = Priority.CRITICAL
        elif temp >= 50:
            priority = Priority.WARNING
        else:
            priority = Priority.HEALTHY

        return self.dashboard_frame(
            "Hottest Drive",
            f"{drive}  {temp}C",
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
        activity = state.get(
            "zfs_activity",
            {},
        ) or {}

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

        if hasattr(self, "activity_history"):
            self.activity_history.append(total)
            self.activity_history = (
                self.activity_history[-16:]
            )

        if total <= 0:
            return self.dashboard_frame(
                "ZFS Activity",
                "Idle",
                Priority.INFO,
            )

        return self.dashboard_pair(
            "ZFS Activity",
            f"R {self.compact_rate(read_rate)}",
            f"W {self.compact_rate(write_rate)}",
            Priority.INFO,
            indicator="*",
        )

    @staticmethod
    def _interface_ipv4_addresses():
        """Return active interface IPv4 addresses."""

        try:
            result = subprocess.run(
                [
                    "ip",
                    "-json",
                    "address",
                    "show",
                    "up",
                ],
                check=True,
                capture_output=True,
                text=True,
                timeout=2,
            )
            interfaces = json.loads(
                result.stdout
            )
        except (
            FileNotFoundError,
            subprocess.SubprocessError,
            json.JSONDecodeError,
        ):
            return {}

        addresses = {}

        for interface in interfaces:
            name = str(
                interface.get("ifname", "")
            )

            if not name or name == "lo":
                continue

            ipv4 = []

            for address in interface.get(
                "addr_info",
                [],
            ):
                if address.get("family") != "inet":
                    continue

                value = address.get("local")

                if value:
                    ipv4.append(str(value))

            if ipv4:
                addresses[name] = ipv4

        return addresses

    @staticmethod
    def _default_route_interface():
        try:
            result = subprocess.run(
                [
                    "ip",
                    "-json",
                    "route",
                    "show",
                    "default",
                ],
                check=True,
                capture_output=True,
                text=True,
                timeout=2,
            )
            routes = json.loads(
                result.stdout
            )
        except (
            FileNotFoundError,
            subprocess.SubprocessError,
            json.JSONDecodeError,
        ):
            return None

        for route in routes:
            device = route.get("dev")

            if device:
                return str(device)

        return None

    @staticmethod
    def _physical_network_interfaces():
        """
        Return every physical Ethernet interface and its current IPv4 state.

        Physical adapters are identified by the presence of a device link in
        /sys/class/net. Virtual bridges, Docker adapters, veth devices,
        loopback, and Tailscale are excluded automatically.
        """
        interfaces = []

        try:
            result = subprocess.run(
                ["ip", "-j", "address", "show"],
                check=True,
                capture_output=True,
                text=True,
            )
            address_data = json.loads(result.stdout)
        except (
            OSError,
            subprocess.CalledProcessError,
            json.JSONDecodeError,
        ):
            address_data = []

        by_name = {
            item.get("ifname"): item
            for item in address_data
            if item.get("ifname")
        }

        sysfs = Path("/sys/class/net")

        try:
            names = sorted(
                entry.name
                for entry in sysfs.iterdir()
                if (entry / "device").exists()
            )
        except OSError:
            names = []

        for position, name in enumerate(names, start=1):
            item = by_name.get(name, {})
            ipv4 = None

            for address in item.get("addr_info", []):
                if address.get("family") != "inet":
                    continue

                candidate = address.get("local")

                if candidate:
                    ipv4 = candidate
                    break

            operstate = str(item.get("operstate", "")).upper()
            flags = set(item.get("flags", []))

            link_up = (
                operstate == "UP"
                or "LOWER_UP" in flags
            )

            interfaces.append(
                {
                    "position": position,
                    "name": name,
                    "ipv4": ipv4,
                    "link_up": link_up,
                    "operstate": operstate or "UNKNOWN",
                }
            )

        return interfaces

    @classmethod
    def _network_display_addresses(cls):
        interfaces = (
            cls._interface_ipv4_addresses()
        )
        default_interface = (
            cls._default_route_interface()
        )

        nas_ip = None
        tailscale_ip = None

        if default_interface:
            values = interfaces.get(
                default_interface,
                [],
            )

            if values:
                nas_ip = values[0]

        for name, values in interfaces.items():
            for value in values:
                try:
                    address = ipaddress.ip_address(
                        value
                    )
                except ValueError:
                    continue

                is_tailscale = (
                    name.startswith("tailscale")
                    or address
                    in ipaddress.ip_network(
                        "100.64.0.0/10"
                    )
                )

                if is_tailscale:
                    tailscale_ip = value
                    continue

                if nas_ip is None and not (
                    address.is_loopback
                    or address.is_link_local
                ):
                    nas_ip = value

        return nas_ip, tailscale_ip

    @staticmethod
    def _server_display_name():
        try:
            name = socket.gethostname().strip()
        except Exception:
            name = ""

        return name or "TrueNAS Server"

    def _dashboard_network(self, state):
        interfaces = self._physical_network_interfaces()

        if not interfaces:
            return self.make_frame(
                self.center_text("Ethernet"),
                "Unavailable",
                Priority.INFO,
            )

        index = self.network_interface_index % len(interfaces)
        interface = interfaces[index]
        self.network_interface_index = (
            self.network_interface_index + 1
        ) % len(interfaces)

        arrow = "↑" if interface["link_up"] else "↓"
        title = f"Ethernet {interface['position']} {arrow}"
        value = interface["ipv4"] or "No IPv4 address"

        return self.make_frame(
            self.center_text(title),
            value,
            Priority.INFO,
        )

    def _dashboard_tailscale(self, state):
        _, tailscale_ip = self._network_display_addresses()

        return self.make_frame(
            self.center_text("Tailscale"),
            tailscale_ip or "Offline",
            Priority.INFO,
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
