"""
TruePanel core plugin.

Registers the built-in dashboard pages supplied by DisplayManager.
"""


class CorePlugin:
    name = "core"
    version = "1.0"

    def register(self, registry):
        registry.register_dashboard_page(
            "home",
            "Mission Home",
        )
        registry.register_dashboard_page(
            "performance",
            "Performance",
        )
        registry.register_dashboard_page(
            "storage",
            "Storage",
        )
        registry.register_dashboard_page(
            "capacity",
            "Capacity",
        )
        registry.register_dashboard_page(
            "activity",
            "ZFS Activity",
        )
        registry.register_dashboard_page(
            "thermal",
            "Thermal",
        )
        registry.register_dashboard_page(
            "smart",
            "SMART",
        )
        registry.register_dashboard_page(
            "network",
            "Network",
        )
