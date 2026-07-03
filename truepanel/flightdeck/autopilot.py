"""
AutoPilot

Owns dashboard rotation behavior for the Flight Deck.

Mission Control decides what matters.
Display Manager knows how to build dashboard frames.
AutoPilot decides when dashboard frames advance.
"""

from time import monotonic


class AutoPilot:
    def __init__(
        self,
        display_manager,
        interval=5,
        pause_time=60,
        idle_slowdown_after=3600,
        idle_interval=30,
    ):
        self.display_manager = display_manager

        self.interval = interval
        self.pause_time = pause_time
        self.idle_slowdown_after = idle_slowdown_after
        self.idle_interval = idle_interval

        now = monotonic()

        self.last_rotation = now
        self.last_interaction = now
        self.pause_until = 0
        self.enabled = True

    def current_interval(self):
        now = monotonic()

        if now - self.last_interaction >= self.idle_slowdown_after:
            return self.idle_interval

        return self.interval

    def frame(self, state):
        """Return the current dashboard frame without advancing."""
        return self.display_manager.render_dashboard(state)

    def next(self, state):
        """Manually advance to the next dashboard frame."""
        self.last_interaction = monotonic()
        self.pause()
        return self.display_manager.next_dashboard(state)

    def previous(self, state):
        """
        Manually move to the previous dashboard frame.

        DisplayManager only exposes next_dashboard(), so we step backwards by
        moving the dashboard index back two positions, then calling next.
        """
        self.last_interaction = monotonic()
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
        """Temporarily pause automatic rotation."""
        self.pause_until = monotonic() + self.pause_time

    def resume(self):
        """Resume automatic rotation immediately."""
        self.pause_until = 0
        self.last_rotation = monotonic()

    def disable(self):
        """Disable automatic dashboard rotation."""
        self.enabled = False

    def enable(self):
        """Enable automatic dashboard rotation."""
        self.enabled = True
        self.last_rotation = monotonic()

    def should_rotate(self):
        if not self.enabled:
            return False

        now = monotonic()

        if now < self.pause_until:
            return False

        return (now - self.last_rotation) >= self.current_interval()

    def tick(self, state):
        """
        Called once per display loop.

        Returns the dashboard frame that should currently be shown.
        """

        if self.should_rotate():
            self.last_rotation = monotonic()
            return self.display_manager.next_dashboard(state)

        return self.frame(state)
