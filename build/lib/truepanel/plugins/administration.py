"""
Plugin installation and local state management.

Plugin API v1 installs local plugin directories or plugin.py files. Remote
marketplace installation is intentionally deferred until signed packages and
trust rules exist.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from .api import normalize_plugin_id


DEFAULT_PLUGIN_ROOT = Path("plugins")
STATE_FILENAME = ".truepanel-plugin-state.json"


def state_path(plugin_root=DEFAULT_PLUGIN_ROOT):
    return Path(plugin_root) / STATE_FILENAME


def load_state(plugin_root=DEFAULT_PLUGIN_ROOT):
    path = state_path(plugin_root)

    if not path.exists():
        return {
            "disabled": [],
            "sources": {},
        }

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        data = {}

    return {
        "disabled": list(data.get("disabled", [])),
        "sources": dict(data.get("sources", {})),
    }


def save_state(state, plugin_root=DEFAULT_PLUGIN_ROOT):
    root = Path(plugin_root)
    root.mkdir(parents=True, exist_ok=True)

    path = state_path(root)
    temporary = path.with_suffix(".tmp")

    temporary.write_text(
        json.dumps(state, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def plugin_destination(plugin_id, plugin_root=DEFAULT_PLUGIN_ROOT):
    return Path(plugin_root) / normalize_plugin_id(plugin_id)


def detect_plugin_id(source):
    source = Path(source)

    if source.is_file():
        return normalize_plugin_id(source.stem)

    return normalize_plugin_id(source.name)


def install_plugin(
    source,
    plugin_root=DEFAULT_PLUGIN_ROOT,
    replace=False,
):
    source = Path(source).expanduser().resolve()

    if not source.exists():
        raise FileNotFoundError(f"Plugin source not found: {source}")

    plugin_id = detect_plugin_id(source)
    destination = plugin_destination(plugin_id, plugin_root)

    if destination.exists():
        if not replace:
            raise FileExistsError(
                f"Plugin already installed: {plugin_id}"
            )

        shutil.rmtree(destination)

    destination.mkdir(parents=True, exist_ok=True)

    if source.is_file():
        if source.suffix != ".py":
            raise ValueError(
                "Single-file plugins must use a .py extension"
            )

        shutil.copy2(source, destination / "plugin.py")
    else:
        plugin_file = source / "plugin.py"

        if not plugin_file.exists():
            raise ValueError(
                "Plugin directory must contain plugin.py"
            )

        for child in source.iterdir():
            target = destination / child.name

            if child.is_dir():
                shutil.copytree(
                    child,
                    target,
                    ignore=shutil.ignore_patterns(
                        "__pycache__",
                        "*.pyc",
                    ),
                )
            else:
                shutil.copy2(child, target)

    state = load_state(plugin_root)
    state["sources"][plugin_id] = str(source)

    if plugin_id in state["disabled"]:
        state["disabled"].remove(plugin_id)

    save_state(state, plugin_root)
    return plugin_id, destination


def update_plugin(plugin_id, plugin_root=DEFAULT_PLUGIN_ROOT):
    plugin_id = normalize_plugin_id(plugin_id)
    state = load_state(plugin_root)
    source = state["sources"].get(plugin_id)

    if not source:
        raise ValueError(
            f"No recorded source for plugin: {plugin_id}"
        )

    return install_plugin(
        source,
        plugin_root=plugin_root,
        replace=True,
    )


def remove_plugin(plugin_id, plugin_root=DEFAULT_PLUGIN_ROOT):
    plugin_id = normalize_plugin_id(plugin_id)
    destination = plugin_destination(plugin_id, plugin_root)

    if not destination.exists():
        raise FileNotFoundError(
            f"Plugin is not installed: {plugin_id}"
        )

    shutil.rmtree(destination)

    state = load_state(plugin_root)
    state["sources"].pop(plugin_id, None)

    if plugin_id in state["disabled"]:
        state["disabled"].remove(plugin_id)

    save_state(state, plugin_root)


def set_enabled(
    plugin_id,
    enabled,
    plugin_root=DEFAULT_PLUGIN_ROOT,
):
    plugin_id = normalize_plugin_id(plugin_id)
    state = load_state(plugin_root)
    disabled = set(state["disabled"])

    if enabled:
        disabled.discard(plugin_id)
    else:
        disabled.add(plugin_id)

    state["disabled"] = sorted(disabled)
    save_state(state, plugin_root)


def is_enabled(plugin_id, plugin_root=DEFAULT_PLUGIN_ROOT):
    state = load_state(plugin_root)
    return normalize_plugin_id(plugin_id) not in state["disabled"]


def installed_plugins(plugin_root=DEFAULT_PLUGIN_ROOT):
    root = Path(plugin_root)

    if not root.exists():
        return []

    return sorted(
        child.name
        for child in root.iterdir()
        if child.is_dir() and (child / "plugin.py").exists()
    )
