"""
Core TruePanel Plugin
"""

from .base import Plugin


class CorePlugin(Plugin):
    name = "Core"
    version = "1.0"
    author = "TruePanel"

    def register(self, registry):
        registry.register_dashboard_page("home", "Mission Home")
        registry.register_dashboard_page("storage", "Storage")
        registry.register_dashboard_page("capacity", "Capacity")
        registry.register_dashboard_page("performance", "Performance")
        registry.register_dashboard_page("thermal", "Thermal")
        registry.register_dashboard_page("smart", "SMART")

        registry.register_theme_pack("default")
        registry.register_theme_pack("tactical")
        registry.register_theme_pack("quiet")
