"""
TruePanel Plugin Manager
"""

import importlib
from pathlib import Path

from .core import CorePlugin
from .registry import Registry
from .simulator import SimulatorPlugin


BUILTIN_PLUGINS = [
    CorePlugin,
    SimulatorPlugin,
]


def load_plugin_class(module):
    if hasattr(module, "Plugin"):
        return module.Plugin

    for value in module.__dict__.values():
        if isinstance(value, type) and value.__name__.endswith("Plugin"):
            return value

    return None


def discover_external_plugins(path="plugins"):
    plugin_path = Path(path)

    if not plugin_path.exists():
        return []

    discovered = []

    for child in plugin_path.iterdir():
        if not child.is_dir():
            continue

        plugin_file = child / "plugin.py"

        if not plugin_file.exists():
            continue

        module_name = f"plugins.{child.name}.plugin"

        try:
            module = importlib.import_module(module_name)
            plugin_class = load_plugin_class(module)

            if plugin_class is not None:
                discovered.append(plugin_class)
        except Exception:
            continue

    return discovered


def load_plugins(config=None):
    registry = Registry()

    plugin_classes = list(BUILTIN_PLUGINS)
    plugin_classes.extend(discover_external_plugins())

    for plugin_class in plugin_classes:
        try:
            plugin = plugin_class()
            plugin.register(registry)
            registry.register_plugin(plugin)
        except Exception:
            continue

    return registry
