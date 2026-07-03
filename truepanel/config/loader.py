"""
TruePanel Configuration Loader
"""

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
        "startup_splash": True,
    },
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
    result = defaults.copy()

    for key, value in overrides.items():
        if (
            key in result
            and isinstance(result[key], dict)
            and isinstance(value, dict)
        ):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value

    return result


def load_config(path="truepanel.yaml"):
    config_path = Path(path)

    if not config_path.exists() or yaml is None:
        return DEFAULT_CONFIG

    try:
        with config_path.open() as f:
            loaded = yaml.safe_load(f) or {}
    except Exception:
        return DEFAULT_CONFIG

    return deep_merge(DEFAULT_CONFIG, loaded)
