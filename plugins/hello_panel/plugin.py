"""
Example TruePanel third-party plugin.
"""

from truepanel.mission_control.constants import Priority
from truepanel.plugins import Plugin


class HelloPanelPlugin(Plugin):
    plugin_id = "hello-panel"
    name = "Hello Panel"
    version = "1.0.0"
    author = "TruePanel Example"
    description = "Example third-party dashboard plugin."
    capabilities = ("dashboard",)

    def register(self, registry):
        registry.register_dashboard_page(
            "hello",
            "Hello Panel",
            renderer=render_hello,
        )


def render_hello(state, display_manager):
    hostname = state.get("hostname", "TruePanel")

    return display_manager.make_frame(
        line1="HELLO PLUGIN",
        line2=str(hostname)[:16],
        priority=Priority.INFO,
    )


Plugin = HelloPanelPlugin
