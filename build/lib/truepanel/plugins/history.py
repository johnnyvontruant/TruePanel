"""
TruePanel Historical LCD Plugin.
"""

from truepanel.history.lcd import HISTORY_RENDERERS
from truepanel.plugins import Plugin


PAGE_TITLES = {
    "history-cpu": "CPU History",
    "history-ram": "RAM History",
    "history-temperature": "Temperature History",
    "history-capacity": "Pool Capacity History",
    "history-network": "Network History",
    "history-zfs": "ZFS Activity History",
    "history-alerts": "Alert History Graph",
}


class HistoricalLCDPlugin(Plugin):
    plugin_id = "history-lcd"
    name = "Historical LCD"
    version = "1.0.0"
    author = "TruePanel"
    description = "Persistent historical telemetry pages for the LCD."
    capabilities = ("dashboard",)

    def register(self, registry):
        config = (
            self.context.config
            if self.context is not None
            else {}
        )

        history_config = config.get("history", {})
        lcd_config = history_config.get("lcd", {})

        if not history_config.get("enabled", True):
            return

        if not lcd_config.get("enabled", True):
            return

        configured_pages = lcd_config.get(
            "pages",
            list(HISTORY_RENDERERS.keys()),
        )

        for page_id in configured_pages:
            renderer = HISTORY_RENDERERS.get(page_id)

            if renderer is None:
                continue

            registry.register_dashboard_page(
                page_id,
                PAGE_TITLES.get(page_id, page_id),
                renderer=renderer,
            )


Plugin = HistoricalLCDPlugin
