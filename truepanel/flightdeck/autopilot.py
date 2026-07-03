"""
AutoPilot

Owns dashboard rotation behavior for the Flight Deck.

Mission Control decides what matters.
Display Manager knows how to build dashboard frames.
AutoPilot decides when dashboard frames advance.

Startup splash and Night Mode behavior are configuration-driven so
FlightDeck policy can evolve without changing Mission Control logic.
"""

from time import monotonic


class FlightMode:
    NORMAL = "normal"
    IDLE = "idle"
    NIGHT = "night"


class AutoPilot:
    def __init__(
        self,
        display_manager,
        interval=5,
        pause_time=60,
        idle_slowdown_after=3600,
        idle_interval=30,
        config=None,
    ):
        self.display_manager = display_manager
        self.config = config or {}

        flightdeck = self.config.get("flightdeck", {})

        self.interval = flightdeck.get("rotation_interval", interval)
        self.pause_time = flightdeck.get("pause_after_button", pause_time)
        self.idle_slowdown_after = flightdeck.get(
            "idle_slowdown_after",
            idle_slowdown_after,
        )
        self.idle_interval = flightdeck.get("idle_interval", idle_interval)

        self.startup_config = flightdeck.get("startup", {})
        self.legacy_startup_splash = flightdeck.get("startup_splash", True)

        self.night_config = flightdeck.get("night_mode", {})
        self.night_enabled = self.night_config.get("enabled", False)
        self.night_idle_after = self.night_config.get("idle_after", 1800)
        self.night_interval = self.night_config.get("rotation_interval", 60)
        self.night_suppress_info = self.night_config.get("suppress_info", True)
        self.night_dashboard_pages = self.night_config.get(
            "dashboard_pages",
            ["home", "storage"],
        )

        now = monotonic()

        self.last_rotation = now
        self.last_interaction = now
        self.pause_until = 0
        self.enabled = True
        self.mode = FlightMode.NORMAL

    def startup_enabled(self):
        return self.startup_config.get("enabled", self.legacy_startup_splash)

    def startup_delay(self):
        return self.startup_config.get("delay", 0.75)

    def startup_frames(self):
        theme = self.config.get("theme", {})

        default_frames = [
            [
                theme.get("startup_title", "TruePanel"),
                theme.get("startup_subtitle", "Flight Deck"),
            ],
            ["Mission Ctrl", "Online"],
            ["Collectors", "Ready"],
            [theme.get("healthy_message", "Mission Ready"), ""],
        ]

        frames = self.startup_config.get("frames", default_frames)

        safe_frames = []

        for frame in frames:
            if not isinstance(frame, (list, tuple)):
                continue

            line1 = str(frame[0]) if len(frame) > 0 else ""
            line2 = str(frame[1]) if len(frame) > 1 else ""

            safe_frames.append([line1[:16], line2[:16]])

        return safe_frames or default_frames

    def current_mode(self):
        now = monotonic()
        idle_time = now - self.last_interaction

        if self.night_enabled and idle_time >= self.night_idle_after:
            self.mode = FlightMode.NIGHT
        elif idle_time >= self.idle_slowdown_after:
            self.mode = FlightMode.IDLE
        else:
            self.mode = FlightMode.NORMAL

        return self.mode

    def current_interval(self):
        mode = self.current_mode()

        if mode == FlightMode.NIGHT:
            return self.night_interval

        if mode == FlightMode.IDLE:
            return self.idle_interval

        return self.interval

    def night_mode_active(self):
        return self.current_mode() == FlightMode.NIGHT

    def wake(self):
        self.last_interaction = monotonic()
        self.mode = FlightMode.NORMAL

    def frame(self, state):
        if self.night_mode_active():
            return self.night_frame(state)

        return self.display_manager.render_dashboard(state)

    def night_frame(self, state):
        current_index = getattr(self.display_manager, "dashboard_index", 0)
        allowed_indexes = self.night_dashboard_indexes()

        if not allowed_indexes:
            return self.display_manager.render_dashboard(state)

        if current_index not in allowed_indexes:
            self.display_manager.dashboard_index = allowed_indexes[0]

        return self.display_manager.render_dashboard(state)

    def night_dashboard_indexes(self):
        page_names = {
            "home": 0,
            "storage": 1,
            "capacity": 2,
            "performance": 3,
            "thermal": 4,
            "smart": 5,
        }

        indexes = []

        for page in self.night_dashboard_pages:
            if page in page_names:
                indexes.append(page_names[page])

        try:
            total = self.display_manager.dashboard_count()
        except AttributeError:
            total = 6

        return [index for index in indexes if index < total]

    def next_night_dashboard(self, state):
        allowed_indexes = self.night_dashboard_indexes()

        if not allowed_indexes:
            return self.display_manager.next_dashboard(state)

        current_index = getattr(self.display_manager, "dashboard_index", 0)

        if current_index not in allowed_indexes:
            self.display_manager.dashboard_index = allowed_indexes[0]
            return self.display_manager.render_dashboard(state)

        position = allowed_indexes.index(current_index)
        next_position = (position + 1) % len(allowed_indexes)
        self.display_manager.dashboard_index = allowed_indexes[next_position]

        return self.display_manager.render_dashboard(state)

    def next(self, state):
        self.wake()
        self.pause()
        return self.display_manager.next_dashboard(state)

    def previous(self, state):
        self.wake()
        self.pause()

        try:
            total = self.display_manager.dashboard_count()
        except AttributeError:
            total = 6

        self.display_manager.dashboard_index = (
            self.display_manager.dashboard_index - 2
        ) % total

        return self.display_manager.next_dashboard(state)

    def pause(self):
        self.pause_until = monotonic() + self.pause_time

    def resume(self):
        self.pause_until = 0
        self.last_rotation = monotonic()
        self.wake()

    def disable(self):
        self.enabled = False

    def enable(self):
        self.enabled = True
        self.last_rotation = monotonic()
        self.wake()

    def should_rotate(self):
        if not self.enabled:
            return False

        now = monotonic()

        if now < self.pause_until:
            return False

        return (now - self.last_rotation) >= self.current_interval()

    def tick(self, state):
        if self.should_rotate():
            self.last_rotation = monotonic()

            if self.night_mode_active():
                return self.next_night_dashboard(state)

            return self.display_manager.next_dashboard(state)

        return self.frame(state)
