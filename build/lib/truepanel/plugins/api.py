"""
TruePanel Plugin API v1.

This module contains the stable public contract intended for third-party
extensions. Plugins should import public objects from truepanel.plugins rather
than importing manager or registry internals.
"""

from __future__ import annotations

import importlib
import platform
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Iterable, Optional


PLUGIN_API_VERSION = "1.0"


class PluginCapability(str, Enum):
    DASHBOARD = "dashboard"
    COLLECTOR = "collector"
    WATCHER = "watcher"
    THEME = "theme"
    NOTIFICATION = "notification"
    MENU = "menu"
    HARDWARE = "hardware"
    SERVICE = "service"
    STARTUP = "startup"


@dataclass(frozen=True)
class PluginManifest:
    plugin_id: str
    name: str
    version: str = "0.1.0"
    author: str = ""
    description: str = ""
    api_version: str = PLUGIN_API_VERSION
    requires_python: str = ">=3.11"
    requires_truepanel: str = ">=0.7"
    requires_modules: tuple[str, ...] = ()
    capabilities: tuple[str, ...] = ()
    homepage: str = ""
    license: str = ""
    builtin: bool = False

    @classmethod
    def from_dict(cls, data: Optional[dict[str, Any]]) -> "PluginManifest":
        data = dict(data or {})

        plugin_id = normalize_plugin_id(
            data.get("plugin_id")
            or data.get("id")
            or data.get("name")
            or "unknown"
        )

        capabilities = tuple(
            str(item).lower()
            for item in data.get("capabilities", ())
        )

        requires_modules = tuple(
            str(item)
            for item in data.get("requires_modules", ())
        )

        return cls(
            plugin_id=plugin_id,
            name=str(data.get("name") or plugin_id),
            version=str(data.get("version", "0.1.0")),
            author=str(data.get("author", "")),
            description=str(data.get("description", "")),
            api_version=str(
                data.get("api_version", PLUGIN_API_VERSION)
            ),
            requires_python=str(
                data.get("requires_python", ">=3.11")
            ),
            requires_truepanel=str(
                data.get("requires_truepanel", ">=0.7")
            ),
            requires_modules=requires_modules,
            capabilities=capabilities,
            homepage=str(data.get("homepage", "")),
            license=str(data.get("license", "")),
            builtin=bool(data.get("builtin", False)),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "plugin_id": self.plugin_id,
            "name": self.name,
            "version": self.version,
            "author": self.author,
            "description": self.description,
            "api_version": self.api_version,
            "requires_python": self.requires_python,
            "requires_truepanel": self.requires_truepanel,
            "requires_modules": list(self.requires_modules),
            "capabilities": list(self.capabilities),
            "homepage": self.homepage,
            "license": self.license,
            "builtin": self.builtin,
        }


@dataclass
class PluginContext:
    config: dict[str, Any]
    plugin_config: dict[str, Any]
    root_path: Path
    plugin_path: Optional[Path] = None
    logger: Any = None
    services: dict[str, Any] = field(default_factory=dict)

    def service(self, name: str, default: Any = None) -> Any:
        return self.services.get(name, default)


@dataclass
class PluginValidation:
    valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def add_error(self, message: str) -> None:
        self.valid = False
        self.errors.append(str(message))

    def add_warning(self, message: str) -> None:
        self.warnings.append(str(message))


@dataclass
class PluginLoadResult:
    plugin_id: str
    name: str
    version: str
    status: str
    source: str
    builtin: bool = False
    error: str = ""
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "plugin_id": self.plugin_id,
            "name": self.name,
            "version": self.version,
            "status": self.status,
            "source": self.source,
            "builtin": self.builtin,
            "error": self.error,
            "warnings": list(self.warnings),
        }


class PluginError(RuntimeError):
    pass


class PluginValidationError(PluginError):
    pass


class PluginCompatibilityError(PluginError):
    pass


class DuplicateRegistrationError(PluginError):
    pass


def normalize_plugin_id(value: Any) -> str:
    normalized = re.sub(
        r"[^a-z0-9._-]+",
        "-",
        str(value or "").strip().lower(),
    )
    return normalized.strip("-._") or "unknown"


def version_tuple(value: str) -> tuple[int, ...]:
    numbers = re.findall(r"\d+", str(value))
    return tuple(int(item) for item in numbers[:4]) or (0,)


def check_simple_specifier(current: str, specifier: str) -> bool:
    """
    Handle the small compatibility subset needed by Plugin API v1.

    Supported forms:
        >=1.0
        >1.0
        <=1.0
        <1.0
        ==1.0
        1.0
    """

    specifier = str(specifier or "").strip()

    if not specifier:
        return True

    operators = (">=", "<=", "==", ">", "<")
    operator = "=="
    expected = specifier

    for candidate in operators:
        if specifier.startswith(candidate):
            operator = candidate
            expected = specifier[len(candidate):].strip()
            break

    left = version_tuple(current)
    right = version_tuple(expected)

    width = max(len(left), len(right))
    left += (0,) * (width - len(left))
    right += (0,) * (width - len(right))

    comparisons: dict[str, Callable[[], bool]] = {
        ">=": lambda: left >= right,
        "<=": lambda: left <= right,
        "==": lambda: left == right,
        ">": lambda: left > right,
        "<": lambda: left < right,
    }

    return comparisons[operator]()


def validate_manifest(
    manifest: PluginManifest,
    truepanel_version: str,
) -> PluginValidation:
    result = PluginValidation(valid=True)

    if manifest.plugin_id == "unknown":
        result.add_error("plugin_id is required")

    if not manifest.name.strip():
        result.add_error("name is required")

    if not check_simple_specifier(
        PLUGIN_API_VERSION,
        f"=={manifest.api_version}",
    ):
        result.add_error(
            "Plugin API mismatch: "
            f"plugin requires {manifest.api_version}, "
            f"TruePanel provides {PLUGIN_API_VERSION}"
        )

    if not check_simple_specifier(
        platform.python_version(),
        manifest.requires_python,
    ):
        result.add_error(
            "Python compatibility failed: "
            f"requires {manifest.requires_python}, "
            f"running {platform.python_version()}"
        )

    if not check_simple_specifier(
        truepanel_version,
        manifest.requires_truepanel,
    ):
        result.add_error(
            "TruePanel compatibility failed: "
            f"requires {manifest.requires_truepanel}, "
            f"running {truepanel_version}"
        )

    valid_capabilities = {
        capability.value
        for capability in PluginCapability
    }

    for capability in manifest.capabilities:
        if capability not in valid_capabilities:
            result.add_error(
                f"Unknown capability: {capability}"
            )

    for module_name in manifest.requires_modules:
        try:
            importlib.import_module(module_name)
        except Exception as error:
            result.add_error(
                f"Required module unavailable: "
                f"{module_name}: {error}"
            )

    if not manifest.capabilities:
        result.add_warning(
            "Plugin does not declare capabilities"
        )

    return result


def manifest_from_plugin(
    plugin: Any,
    builtin: bool = False,
) -> PluginManifest:
    declared = getattr(plugin, "manifest", None)

    if isinstance(declared, PluginManifest):
        if builtin and not declared.builtin:
            values = declared.as_dict()
            values["builtin"] = True
            return PluginManifest.from_dict(values)

        return declared

    if isinstance(declared, dict):
        values = dict(declared)
    else:
        values = {}

    class_name = plugin.__class__.__name__
    legacy_name = getattr(plugin, "name", class_name)

    values.setdefault(
        "plugin_id",
        getattr(plugin, "plugin_id", normalize_plugin_id(legacy_name)),
    )
    values.setdefault("name", legacy_name)
    values.setdefault(
        "version",
        getattr(plugin, "version", "legacy"),
    )
    values.setdefault(
        "author",
        getattr(plugin, "author", ""),
    )
    values.setdefault(
        "description",
        getattr(plugin, "description", ""),
    )
    values.setdefault(
        "api_version",
        getattr(plugin, "api_version", PLUGIN_API_VERSION),
    )
    values.setdefault(
        "capabilities",
        getattr(plugin, "capabilities", ()),
    )
    values["builtin"] = builtin

    return PluginManifest.from_dict(values)


def ensure_iterable_strings(
    values: Optional[Iterable[Any]],
) -> tuple[str, ...]:
    return tuple(str(value) for value in (values or ()))
