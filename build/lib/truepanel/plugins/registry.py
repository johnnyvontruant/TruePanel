"""
TruePanel Plugin Registry.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any

from .api import DuplicateRegistrationError


class Registry:
    def __init__(self):
        self.plugins = []
        self.plugin_instances = {}
        self.plugin_results = []
        self.failed_plugins = []
        self.disabled_plugins = []

        self.collectors = {}
        self.dashboard_pages = []
        self.watchers = []
        self.startup_frames = []
        self.theme_packs = []
        self.menu_items = []
        self.hardware = []
        self.services = []
        self.notifications = {}

        self._active_plugin_id = "core"
        self._dashboard_ids = set()
        self._watcher_ids = set()

    @contextmanager
    def plugin_scope(self, plugin_id):
        previous = self._active_plugin_id
        self._active_plugin_id = str(plugin_id)

        try:
            yield
        finally:
            self._active_plugin_id = previous

    def owner(self):
        return self._active_plugin_id

    def register_plugin(
        self,
        plugin,
        manifest=None,
        status="loaded",
        source="builtin",
    ):
        manifest_dict = (
            manifest.as_dict()
            if hasattr(manifest, "as_dict")
            else dict(manifest or {})
        )

        plugin_id = manifest_dict.get(
            "plugin_id",
            getattr(plugin, "plugin_id", plugin.__class__.__name__),
        )

        record = {
            "plugin_id": plugin_id,
            "name": manifest_dict.get(
                "name",
                getattr(plugin, "name", plugin.__class__.__name__),
            ),
            "version": manifest_dict.get(
                "version",
                getattr(plugin, "version", "unknown"),
            ),
            "author": manifest_dict.get(
                "author",
                getattr(plugin, "author", ""),
            ),
            "description": manifest_dict.get(
                "description",
                getattr(plugin, "description", ""),
            ),
            "capabilities": manifest_dict.get(
                "capabilities",
                [],
            ),
            "builtin": bool(
                manifest_dict.get("builtin", source == "builtin")
            ),
            "status": status,
            "source": source,
        }

        self.plugins.append(record)
        self.plugin_instances[plugin_id] = plugin
        return record

    def add_result(self, result):
        data = (
            result.as_dict()
            if hasattr(result, "as_dict")
            else dict(result)
        )
        self.plugin_results.append(data)

        if data.get("status") == "failed":
            self.failed_plugins.append(data)

        if data.get("status") == "disabled":
            self.disabled_plugins.append(data)

    def register_collector(self, name, factory):
        name = str(name)

        if name in self.collectors:
            raise DuplicateRegistrationError(
                f"Collector already registered: {name}"
            )

        self.collectors[name] = factory

    def register_dashboard_page(
        self,
        page_id,
        title=None,
        renderer=None,
    ):
        page_id = str(page_id)

        if page_id in self._dashboard_ids:
            raise DuplicateRegistrationError(
                f"Dashboard page already registered: {page_id}"
            )

        self._dashboard_ids.add(page_id)
        self.dashboard_pages.append(
            {
                "id": page_id,
                "title": title or page_id,
                "renderer": renderer,
                "plugin_id": self.owner(),
            }
        )

    def register_watcher(self, watcher, watcher_id=None):
        watcher_id = watcher_id or getattr(
            watcher,
            "__name__",
            watcher.__class__.__name__,
        )

        if watcher_id in self._watcher_ids:
            raise DuplicateRegistrationError(
                f"Watcher already registered: {watcher_id}"
            )

        self._watcher_ids.add(watcher_id)
        self.watchers.append(
            {
                "id": watcher_id,
                "watcher": watcher,
                "plugin_id": self.owner(),
            }
        )

    def register_startup_frame(self, line1, line2=""):
        self.startup_frames.append(
            {
                "lines": [str(line1)[:16], str(line2)[:16]],
                "plugin_id": self.owner(),
            }
        )

    def register_theme_pack(self, name, path=None):
        record = {
            "name": str(name),
            "path": str(path) if path else "",
            "plugin_id": self.owner(),
        }

        if record not in self.theme_packs:
            self.theme_packs.append(record)

    def register_notification(self, name, provider):
        name = str(name)

        if name in self.notifications:
            raise DuplicateRegistrationError(
                f"Notification provider already registered: {name}"
            )

        self.notifications[name] = {
            "provider": provider,
            "plugin_id": self.owner(),
        }

    def register_menu_item(self, item):
        self.menu_items.append(
            {
                "item": item,
                "plugin_id": self.owner(),
            }
        )

    def register_hardware(self, item):
        self.hardware.append(
            {
                "item": item,
                "plugin_id": self.owner(),
            }
        )

    def register_service(self, name, service=None):
        if service is None:
            service = name
            name = getattr(
                service,
                "name",
                service.__class__.__name__,
            )

        self.services.append(
            {
                "name": str(name),
                "service": service,
                "plugin_id": self.owner(),
            }
        )

    def get_plugin(self, plugin_id):
        return self.plugin_instances.get(plugin_id)

    def summary(self):
        return {
            "plugins": self.plugins,
            "collectors": sorted(self.collectors.keys()),
            "dashboard_pages": [
                {
                    "id": page["id"],
                    "title": page["title"],
                    "plugin_id": page.get("plugin_id", ""),
                }
                for page in self.dashboard_pages
            ],
            "watchers": [
                {
                    "id": watcher["id"],
                    "plugin_id": watcher["plugin_id"],
                }
                for watcher in self.watchers
            ],
            "startup_frames": len(self.startup_frames),
            "theme_packs": self.theme_packs,
            "notifications": sorted(self.notifications.keys()),
            "menu_items": len(self.menu_items),
            "hardware": len(self.hardware),
            "services": len(self.services),
            "failed_plugins": self.failed_plugins,
            "disabled_plugins": self.disabled_plugins,
        }
