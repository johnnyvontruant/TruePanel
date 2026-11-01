"""
TruePanel public Plugin API.
"""

from .api import (
    PLUGIN_API_VERSION,
    DuplicateRegistrationError,
    PluginCapability,
    PluginCompatibilityError,
    PluginContext,
    PluginError,
    PluginLoadResult,
    PluginManifest,
    PluginValidation,
    PluginValidationError,
)
from .base import Plugin


def load_plugins(config=None):
    """
    Load plugins lazily to prevent collector/plugin import cycles.
    """

    from .manager import load_plugins as manager_load_plugins

    return manager_load_plugins(config)


__all__ = [
    "PLUGIN_API_VERSION",
    "DuplicateRegistrationError",
    "Plugin",
    "PluginCapability",
    "PluginCompatibilityError",
    "PluginContext",
    "PluginError",
    "PluginLoadResult",
    "PluginManifest",
    "PluginValidation",
    "PluginValidationError",
    "load_plugins",
]
