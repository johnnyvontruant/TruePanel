import os
import platform
from truepanel.menu.page import Page


class AboutPage(Page):
    title = "About"

    def render(self, state=None):
        return ["TruePanel", "Docker Mode" if os.path.exists("/.dockerenv") else "Native Mode"]


class HostPage(Page):
    title = "Host"

    def render(self, state=None):
        return [
            platform.node()[:16],
            platform.machine()[:16],
        ]
