"""
AutoPilot

Owns the dashboard rotation for the Flight Deck.

Mission Control decides WHAT should be displayed.
AutoPilot decides WHEN dashboard cards advance.
"""

from time import monotonic


class AutoPilot:
    def __init__(self, display_manager, interval=5, pause_time=60):
        self.display_manager = display_manager

        self.interval = interval
        self.pause_time = pause_time

        self.last_rotation = monotonic()
        self.pause_until = 0

    def current_frame(self, state):
        """Return the current dashboard card."""
        return self.display_manager.render_dashboard(state)

    def next_frame(self, state):
        """Advance to the next dashboard card."""
        return self.display_manager.next_dashboard(state)

    def pause(self):
        """Pause automatic rotation after manual navigation."""
        self.pause_until = monotonic() + self.pause_time

    def should_rotate(self):
        now = monotonic()

        if now < self.pause_until:
            return False

        return (now - self.last_rotation) >= self.interval

    def update(self, state):
        """
        Called once each LCD refresh.

        Returns the dashboard frame that should currently be displayed.
        """

        if self.should_rotate():
            self.last_rotation = monotonic()
            return self.next_frame(state)

        return self.current_frame(state)
