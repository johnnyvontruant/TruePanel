"""
TruePanel Plugin Registry
"""


class Registry:
    def __init__(self):
        self.plugins = []
        self.collectors = {}
        self.dashboard_pages = []
        self.watchers = []
        self.startup_frames = []
        self.theme_packs = []
        self.menu_items = []
        self.hardware = []
        self.services = []

    def register_plugin(self, plugin):
        self.plugins.append({
            "name": getattr(plugin, "name", plugin.__class__.__name__),
            "version": getattr(plugin, "version", "unknown"),
            "author": getattr(plugin, "author", ""),
        })

    def register_collector(self, name, factory):
        self.collectors[name] = factory

    def register_dashboard_page(self, page_id, title=None, renderer=None):
        self.dashboard_pages.append({
            "id": page_id,
            "title": title or page_id,
            "renderer": renderer,
        })

    def register_watcher(self, watcher):
        self.watchers.append(watcher)

    def register_startup_frame(self, line1, line2=""):
        self.startup_frames.append([str(line1)[:16], str(line2)[:16]])

    def register_theme_pack(self, name):
        self.theme_packs.append(name)

    def register_menu_item(self, item):
        self.menu_items.append(item)

    def register_hardware(self, item):
        self.hardware.append(item)

    def register_service(self, item):
        self.services.append(item)

    def summary(self):
        return {
            "plugins": self.plugins,
            "collectors": sorted(self.collectors.keys()),
            "dashboard_pages": [
                {
                    "id": page["id"],
                    "title": page["title"],
                }
                for page in self.dashboard_pages
            ],
            "watchers": len(self.watchers),
            "startup_frames": len(self.startup_frames),
            "theme_packs": self.theme_packs,
            "menu_items": len(self.menu_items),
            "hardware": len(self.hardware),
            "services": len(self.services),
        }
