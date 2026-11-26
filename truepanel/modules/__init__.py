"""TruePanel modules: installable features with one shared catalog.

See docs/MODULES.md.
"""

from .catalog import (
    CATALOG,
    CORE,
    DEVELOPER,
    MODULES,
    OPTIONAL,
    RECOMMENDED,
    TIER_LABELS,
    TIERS,
    Module,
    get_module,
    modules_in_tier,
    validate_catalog,
)
from .selection import (
    LEGACY_INSTALLED,
    PRESET_LABELS,
    PRESETS,
    ModuleSelection,
    dependents_of,
    is_module_enabled,
    resolve,
    selection_for_preset,
    selection_from_config,
)

__all__ = [
    "CATALOG",
    "CORE",
    "DEVELOPER",
    "LEGACY_INSTALLED",
    "MODULES",
    "OPTIONAL",
    "PRESETS",
    "PRESET_LABELS",
    "RECOMMENDED",
    "TIERS",
    "TIER_LABELS",
    "Module",
    "ModuleSelection",
    "dependents_of",
    "get_module",
    "is_module_enabled",
    "modules_in_tier",
    "resolve",
    "selection_for_preset",
    "selection_from_config",
    "validate_catalog",
]
