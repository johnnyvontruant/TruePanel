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
    "history": {
        "enabled": True,
        "path": "/var/lib/truepanel/history/telemetry.jsonl",
        "sample_interval": 60,
        "retention_days": 30,
        "max_samples": 50000,
        "compact_every": 250,
        "flush": False,
        "lcd": {
            "enabled": True,
            "window_hours": 1,
            "points": 16,
            "pages": [
                "history-cpu",
                "history-ram",
                "history-temperature",
                "history-capacity",
                "history-network",
                "history-zfs",
                "history-alerts",
            ],
        },
    },
    "plugins": {
        "path": "plugins",
        "external_enabled": True,
        "disabled": [],
        "config": {},
    },
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
        "mission_ready": "MISSION READY",
        "all_systems_go": "All Systems GO",
        "pool_healthy": "POOLS ONLINE",
        "system_watch": "SYSTEM WATCH",
        "alert_banner": "SYSTEM ALERT",
        "warning_banner": "WARNING",
        "warning_prefix": "! ",
        "critical_prefix": "X ",
        "info_prefix": "i ",
        "healthy_prefix": "O ",
    },
    "graphics": {
        "filled": "#",
        "empty": "-",
        "healthy": "O",
        "info": "i",
        "warning": "!",
        "critical": "X",
        "activity_low": ".",
        "activity_mid": "=",
        "activity_high": "#",
    },
    "buzzer": {
        "enabled": True,
        "backend": "serial_opcode",
        "port": "/dev/ttyS1",
        "speed": 1200,
        "startup": "long",
        "shutdown": "short",
        "warning": "short",
        "critical": "long",
        "cooldown": 30,
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
