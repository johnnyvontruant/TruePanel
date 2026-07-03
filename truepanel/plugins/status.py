"""
Plugin Status Plugin
"""

from .base import Plugin
from truepanel.mission_control.constants import Priority


class PluginStatusPlugin(Plugin):
    name = "Plugin Status"
    version = "1.0"
    author = "TruePanel"

    def register(self, registry):
        registry.register_dashboard_page(
            "plugins",
            "Plugins",
            renderer=render_plugin_status,
        )


def render_plugin_status(state, display_manager):
    registry = display_manager.registry

    plugin_count = len(getattr(registry, "plugins", []))
    collector_count = len(getattr(registry, "collectors", {}))

    return display_manager.make_frame(
        line1="Plugins",
        line2=f"{plugin_count} Plug {collector_count} Col",
        priority=Priority.INFO,
    )
