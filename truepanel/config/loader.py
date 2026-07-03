"""
TruePanel Configuration Loader

Loads truepanel.yaml, merges it with defaults, then applies an optional
theme pack before user-level theme overrides.
"""

from copy import deepcopy
from pathlib import Path

try:
    import yaml
except Exception:
    yaml = None


DEFAULT_CONFIG = {
    "flightdeck": {
        "rotation_interval": 5,
        "pause_after_button": 60,
        "idle_slowdown_after": 3600,
        "idle_interval": 30,
        "startup": {
            "enabled": True,
            "delay": 0.75,
            "frames": [
                ["TruePanel", "Flight Deck"],
                ["Mission Ctrl", "Online"],
                ["Collectors", "Ready"],
                ["Mission Ready", ""],
            ],
        },
        "night_mode": {
            "enabled": True,
            "idle_after": 1800,
            "rotation_interval": 60,
            "suppress_info": True,
            "dashboard_pages": ["home", "storage"],
        },
    },
    "theme_pack": "default",
    "theme": {
        "healthy_message": "Mission Ready",
        "startup_title": "TruePanel",
        "startup_subtitle": "Flight Deck",
        "warning_prefix": "! ",
        "critical_prefix": "!!",
        "info_prefix": "i ",
        "healthy_prefix": "OK",
    },
}


def deep_merge(defaults, overrides):
    result = deepcopy(defaults)

    for key, value in (overrides or {}).items():
        if (
            key in result
            and isinstance(result[key], dict)
            and isinstance(value, dict)
        ):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = deepcopy(value)

    return result


def load_yaml(path):
    yaml_path = Path(path)

    if not yaml_path.exists() or yaml is None:
        return {}

    try:
        with yaml_path.open() as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}


def load_theme_pack(name):
    if not name:
        return {}

    safe_name = str(name).replace("/", "").replace("\\", "")
    theme_path = Path(__file__).resolve().parent.parent / "themes" / "packs" / f"{safe_name}.yaml"

    return load_yaml(theme_path)


def apply_theme_pack(config):
    theme_pack_name = config.get("theme_pack", "default")
    theme_pack = load_theme_pack(theme_pack_name)

    if not theme_pack:
        return config

    user_theme = config.get("theme", {})
    packed_config = deep_merge(config, theme_pack)
    packed_config["theme"] = deep_merge(packed_config.get("theme", {}), user_theme)

    return packed_config


def load_config(path="truepanel.yaml"):
    loaded = load_yaml(path)
    config = deep_merge(DEFAULT_CONFIG, loaded)
    return apply_theme_pack(config)
