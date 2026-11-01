"""
TruePanel Plugin Base Class.
"""

from __future__ import annotations

from typing import Any

from .api import (
    PLUGIN_API_VERSION,
    PluginContext,
    PluginManifest,
    manifest_from_plugin,
    validate_manifest,
)


class Plugin:
    """
    Base class for TruePanel plugins.

    Third-party plugins should subclass Plugin and implement register().
    Existing legacy plugins remain supported by the plugin manager.
    """

    plugin_id = ""
    name = "Unnamed Plugin"
    version = "0.1.0"
    author = ""
    description = ""
    api_version = PLUGIN_API_VERSION
    capabilities: tuple[str, ...] = ()

    def __init__(self) -> None:
        self.context: PluginContext | None = None

    @property
    def manifest(self) -> PluginManifest:
        return PluginManifest.from_dict(
            {
                "plugin_id": self.plugin_id or self.name,
                "name": self.name,
                "version": self.version,
                "author": self.author,
                "description": self.description,
                "api_version": self.api_version,
                "capabilities": self.capabilities,
            }
        )

    def configure(self, context: PluginContext) -> None:
        self.context = context

    def validate(self, truepanel_version: str):
        return validate_manifest(
            manifest_from_plugin(self),
            truepanel_version,
        )

    def register(self, registry: Any) -> None:
        raise NotImplementedError(
            f"{self.__class__.__name__}.register() "
            "must be implemented"
        )

    def start(self) -> None:
        """Optional lifecycle hook called after registration."""

    def stop(self) -> None:
        """Optional lifecycle hook called during shutdown."""

    def health(self) -> dict[str, Any]:
        return {
            "healthy": True,
            "message": "Plugin operational",
        }
