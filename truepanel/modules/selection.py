"""Work out which modules are installed from truepanel.yaml.

The ``modules:`` section records what is installed::

    modules:
      installed:
        - hardware_control
        - guided_recovery
        - cargo_bay

Rules:

* Core modules are always installed, listed or not.
* A module's requirements are added automatically, with a reason.
* Unknown ids are reported and ignored, never fatal.
* No ``modules:`` section (or no ``installed:`` list) means a TruePanel
  configuration from before modules existed. Everything stays installed
  so upgrading changes nothing until the operator chooses.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

from .catalog import CATALOG, CORE, DEVELOPER, MODULES, OPTIONAL, RECOMMENDED

PRESETS: dict[str, tuple[str, ...]] = {
    "essentials": tuple(m.id for m in CATALOG if m.tier == CORE),
    "recommended": tuple(m.id for m in CATALOG if m.tier in (CORE, RECOMMENDED)),
    "everything": tuple(
        m.id for m in CATALOG if m.tier in (CORE, RECOMMENDED, OPTIONAL)
    ),
}

PRESET_LABELS = {
    "essentials": "Essentials: LCD, Mission Control and fault alerts only",
    "recommended": "Recommended: Essentials plus hardware control, recovery and intelligence",
    "everything": "Everything: Recommended plus Cargo Bay, Loadmaster and VPN status",
}

# Pre-module installs keep every feature, developer tools included.
LEGACY_INSTALLED = tuple(m.id for m in CATALOG)


@dataclass(frozen=True)
class ModuleSelection:
    installed: frozenset[str]
    # module id -> plain reason it was added automatically
    auto_added: Mapping[str, str] = field(default_factory=dict)
    unknown: tuple[str, ...] = ()
    legacy: bool = False

    def is_installed(self, module_id: str) -> bool:
        if module_id not in MODULES:
            raise KeyError(f"Unknown TruePanel module: {module_id}")
        return module_id in self.installed

    def ordered(self) -> tuple[str, ...]:
        """Installed ids in catalog order, for stable display and config."""
        return tuple(m.id for m in CATALOG if m.id in self.installed)

    def to_config(self) -> dict:
        """The ``modules:`` section that records this selection.

        Core modules are left out: they are always installed.
        """
        return {
            "installed": [
                module_id
                for module_id in self.ordered()
                if MODULES[module_id].tier != CORE
            ]
        }


def _close_over_requirements(
    requested: Iterable[str],
) -> tuple[set[str], dict[str, str]]:
    installed: set[str] = set()
    auto_added: dict[str, str] = {}
    pending = list(requested)
    while pending:
        module_id = pending.pop()
        if module_id in installed:
            continue
        installed.add(module_id)
        for required in MODULES[module_id].requires:
            if required not in installed and required not in pending:
                auto_added.setdefault(
                    required,
                    f"needed by {MODULES[module_id].name}",
                )
                pending.append(required)
    return installed, auto_added


def resolve(requested: Iterable[str], *, legacy: bool = False) -> ModuleSelection:
    """Resolve requested ids into a complete, consistent selection."""
    known: list[str] = []
    unknown: list[str] = []
    for raw in requested:
        module_id = str(raw).strip()
        if not module_id:
            continue
        (known if module_id in MODULES else unknown).append(module_id)

    core = [m.id for m in CATALOG if m.tier == CORE]
    installed, auto_added = _close_over_requirements([*core, *known])
    # Something the operator asked for explicitly was not "auto added".
    for module_id in known:
        auto_added.pop(module_id, None)
    for module_id in core:
        auto_added.pop(module_id, None)

    return ModuleSelection(
        installed=frozenset(installed),
        auto_added=auto_added,
        unknown=tuple(dict.fromkeys(unknown)),
        legacy=legacy,
    )


def selection_from_config(config: Mapping | None) -> ModuleSelection:
    section = (config or {}).get("modules")
    if not isinstance(section, Mapping) or "installed" not in section:
        return resolve(LEGACY_INSTALLED, legacy=True)
    listed = section.get("installed") or []
    if isinstance(listed, str):
        listed = [listed]
    if not isinstance(listed, (list, tuple)):
        listed = []
    return resolve(listed)


def selection_for_preset(name: str, extra: Iterable[str] = ()) -> ModuleSelection:
    try:
        base = PRESETS[name]
    except KeyError:
        raise KeyError(f"Unknown preset: {name}") from None
    return resolve([*base, *extra])


def dependents_of(module_id: str, installed: Iterable[str]) -> tuple[str, ...]:
    """Installed modules that would break if ``module_id`` were removed."""
    found: list[str] = []
    installed = set(installed)
    changed = True
    blocked = {module_id}
    while changed:
        changed = False
        for candidate in installed - blocked:
            if blocked & set(MODULES[candidate].requires):
                blocked.add(candidate)
                found.append(candidate)
                changed = True
    order = {m.id: i for i, m in enumerate(CATALOG)}
    return tuple(sorted(found, key=order.__getitem__))


def is_module_enabled(config: Mapping | None, module_id: str) -> bool:
    """Convenience check for wiring code in later releases."""
    return selection_from_config(config).is_installed(module_id)


__all__ = [
    "DEVELOPER",
    "LEGACY_INSTALLED",
    "PRESETS",
    "PRESET_LABELS",
    "ModuleSelection",
    "dependents_of",
    "is_module_enabled",
    "resolve",
    "selection_for_preset",
    "selection_from_config",
]
