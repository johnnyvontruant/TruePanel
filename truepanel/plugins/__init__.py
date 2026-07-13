"""
TruePanel plugin system.

Plugin loading is intentionally imported lazily. This prevents a circular
import between the plugin manager and collector factory during application
startup.
"""


def load_plugins(config=None):
    """Load and return the configured TruePanel plugin registry."""

    from .manager import load_plugins as manager_load_plugins

    return manager_load_plugins(config)


__all__ = ["load_plugins"]
