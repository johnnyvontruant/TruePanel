"""
TruePanel Plugin Manager v1.
"""

from __future__ import annotations

import importlib.util
import logging
import sys
import traceback
from pathlib import Path
from types import ModuleType
from typing import Any

from truepanel import __version__

from .administration import load_state
from .api import (
    PLUGIN_API_VERSION,
    PluginCompatibilityError,
    PluginContext,
    PluginLoadResult,
    PluginManifest,
    PluginValidationError,
    manifest_from_plugin,
    normalize_plugin_id,
    validate_manifest,
)
from .registry import Registry


LOGGER = logging.getLogger("truepanel.plugins")


def builtin_plugin_classes():
    """
    Import built-ins lazily to prevent plugin/collector import loops.
    """

    from .core import CorePlugin
    from .simulator import SimulatorPlugin
    from .status import PluginStatusPlugin

    return [
        CorePlugin,
        SimulatorPlugin,
        PluginStatusPlugin,
    ]


def load_yaml_manifest(path):
    path = Path(path)

    try:
        import yaml
    except Exception:
        return {}

    if not path.exists():
        return {}

    try:
        with path.open(encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}
    except Exception:
        return {}

    return data if isinstance(data, dict) else {}


def load_plugin_class(module: ModuleType):
    if hasattr(module, "Plugin"):
        candidate = module.Plugin

        if isinstance(candidate, type):
            return candidate

    candidates = []

    for value in module.__dict__.values():
        if (
            isinstance(value, type)
            and value.__module__ == module.__name__
            and value.__name__.endswith("Plugin")
        ):
            candidates.append(value)

    if len(candidates) == 1:
        return candidates[0]

    if not candidates:
        return None

    raise PluginValidationError(
        "Multiple plugin classes found. "
        "Export the intended class as Plugin."
    )


def discover_external_plugins(path="plugins"):
    plugin_root = Path(path)

    if not plugin_root.exists():
        return []

    discovered = []

    for child in sorted(plugin_root.iterdir()):
        if not child.is_dir():
            continue

        plugin_file = child / "plugin.py"

        if plugin_file.exists():
            discovered.append(
                {
                    "plugin_id": normalize_plugin_id(child.name),
                    "path": child,
                    "plugin_file": plugin_file,
                    "manifest_file": child / "plugin.yaml",
                }
            )

    return discovered


def import_external_module(plugin_id, plugin_file):
    module_name = (
        "truepanel_external_plugins."
        + normalize_plugin_id(plugin_id).replace("-", "_")
    )

    spec = importlib.util.spec_from_file_location(
        module_name,
        plugin_file,
        submodule_search_locations=[str(plugin_file.parent)],
    )

    if spec is None or spec.loader is None:
        raise ImportError(
            f"Unable to create module spec for {plugin_file}"
        )

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module

    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(module_name, None)
        raise

    return module


def build_context(
    config,
    plugin_id,
    root_path,
    plugin_path=None,
):
    plugin_config = (
        config.get("plugins", {})
        .get("config", {})
        .get(plugin_id, {})
    )

    return PluginContext(
        config=config,
        plugin_config=plugin_config,
        root_path=Path(root_path).resolve(),
        plugin_path=(
            Path(plugin_path).resolve()
            if plugin_path
            else None
        ),
        logger=logging.getLogger(
            f"truepanel.plugins.{plugin_id}"
        ),
        services={},
    )


def apply_external_manifest(plugin, manifest_file):
    data = load_yaml_manifest(manifest_file)

    if not data:
        return manifest_from_plugin(plugin)

    declared = manifest_from_plugin(plugin).as_dict()
    declared.update(data)

    return PluginManifest.from_dict(declared)


def load_one_plugin(
    registry,
    plugin_class,
    config,
    source,
    builtin=False,
    plugin_path=None,
    external_manifest=None,
):
    plugin = plugin_class()

    manifest = (
        external_manifest
        if external_manifest is not None
        else manifest_from_plugin(plugin, builtin=builtin)
    )

    validation = validate_manifest(
        manifest,
        truepanel_version=__version__,
    )

    if not validation.valid:
        raise PluginCompatibilityError(
            "; ".join(validation.errors)
        )

    context = build_context(
        config=config,
        plugin_id=manifest.plugin_id,
        root_path=Path.cwd(),
        plugin_path=plugin_path,
    )

    configure = getattr(plugin, "configure", None)

    if callable(configure):
        configure(context)
    else:
        plugin.context = context

    with registry.plugin_scope(manifest.plugin_id):
        plugin.register(registry)

    registry.register_plugin(
        plugin,
        manifest=manifest,
        source=source,
    )

    start = getattr(plugin, "start", None)

    if callable(start):
        start()

    result = PluginLoadResult(
        plugin_id=manifest.plugin_id,
        name=manifest.name,
        version=manifest.version,
        status="loaded",
        source=source,
        builtin=builtin,
        warnings=validation.warnings,
    )
    registry.add_result(result)
    return result


def load_plugins(config=None):
    config = config or {}
    plugin_config = config.get("plugins", {})

    plugin_root = Path(
        plugin_config.get("path", "plugins")
    )
    external_enabled = bool(
        plugin_config.get("external_enabled", True)
    )

    state = load_state(plugin_root)
    disabled = set(state.get("disabled", []))
    disabled.update(
        normalize_plugin_id(item)
        for item in plugin_config.get("disabled", [])
    )

    registry = Registry()

    for plugin_class in builtin_plugin_classes():
        try:
            load_one_plugin(
                registry=registry,
                plugin_class=plugin_class,
                config=config,
                source="builtin",
                builtin=True,
            )
        except Exception as error:
            plugin_id = normalize_plugin_id(
                getattr(
                    plugin_class,
                    "plugin_id",
                    plugin_class.__name__,
                )
            )

            LOGGER.error(
                "Built-in plugin %s failed: %s",
                plugin_id,
                error,
            )

            registry.add_result(
                PluginLoadResult(
                    plugin_id=plugin_id,
                    name=getattr(
                        plugin_class,
                        "name",
                        plugin_class.__name__,
                    ),
                    version=str(
                        getattr(plugin_class, "version", "unknown")
                    ),
                    status="failed",
                    source="builtin",
                    builtin=True,
                    error=str(error),
                )
            )

    if not external_enabled:
        return registry

    for discovered in discover_external_plugins(plugin_root):
        plugin_id = discovered["plugin_id"]

        if plugin_id in disabled:
            registry.add_result(
                PluginLoadResult(
                    plugin_id=plugin_id,
                    name=plugin_id,
                    version="unknown",
                    status="disabled",
                    source=str(discovered["path"]),
                )
            )
            continue

        try:
            module = import_external_module(
                plugin_id,
                discovered["plugin_file"],
            )
            plugin_class = load_plugin_class(module)

            if plugin_class is None:
                raise PluginValidationError(
                    "No plugin class found"
                )

            plugin = plugin_class()
            manifest = apply_external_manifest(
                plugin,
                discovered["manifest_file"],
            )

            load_one_plugin(
                registry=registry,
                plugin_class=plugin_class,
                config=config,
                source=str(discovered["path"]),
                builtin=False,
                plugin_path=discovered["path"],
                external_manifest=manifest,
            )
        except Exception as error:
            LOGGER.error(
                "Plugin %s failed: %s",
                plugin_id,
                error,
            )
            LOGGER.debug(
                "Plugin traceback:\n%s",
                traceback.format_exc(),
            )

            registry.add_result(
                PluginLoadResult(
                    plugin_id=plugin_id,
                    name=plugin_id,
                    version="unknown",
                    status="failed",
                    source=str(discovered["path"]),
                    error=str(error),
                )
            )

    return registry
