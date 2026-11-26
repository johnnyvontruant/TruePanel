"""How modules show up in Mission Control.

Kept as data so the server code stays a thin lookup. When a module is
not installed:

* its API routes and scripts answer 404 ``module_not_installed``;
* its companion scripts are not added to the dashboard;
* its panels are hidden with CSS. They are hidden rather than removed
  because some dashboard renderers write to their elements
  unconditionally.
"""

from __future__ import annotations

import json
from collections.abc import Mapping

from .catalog import MODULES
from .selection import ModuleSelection

# Exact request paths owned by an optional module.
ROUTE_MODULES: Mapping[str, str] = {
    "/api/v1/loadmaster": "loadmaster",
    "/api/v1/loadmaster/plan": "loadmaster",
    "/api/v1/loadmaster/command": "loadmaster",
    "/api/v1/fans/profile": "hardware_control",
    "/api/v1/fans/thermal-arm": "hardware_control",
    "/api/v1/lifeline/identify": "hardware_control",
    "/api/v1/recovery/transition": "guided_recovery",
    "/recovery-workflow.js": "guided_recovery",
    "/reliability-view.js": "reliability",
}

# Dashboard elements that belong to an optional module.
PANEL_SELECTORS: Mapping[str, tuple[str, ...]] = {
    "cargo_bay": ("#cardCargoBay",),
    "loadmaster": ("#cardLoadmaster",),
    "hardware_control": ("#cardCooling .control-panel",),
    "vpn_status": (".vpn-interface",),
    "reliability": ("#aegisReliabilityView", "#sentinelFlightDirector"),
    "observatory": ("#observatoryCurrentActivity",),
    "guided_recovery": ("#pathfinderRecoveryDeck",),
}

MODULES_MARKER = b"<!-- truepanel-modules -->"


def module_for_path(path: str) -> str | None:
    return ROUTE_MODULES.get(path)


def not_installed_payload(module_id: str) -> dict:
    module = MODULES[module_id]
    return {
        "error": "module_not_installed",
        "module": module_id,
        "name": module.name,
        "message": f"{module.name} is not installed on this TruePanel.",
    }


def status_payload(selection: ModuleSelection) -> dict:
    """The ``modules`` object published in /api/v1/status."""
    return {
        "legacy": selection.legacy,
        "installed": list(selection.ordered()),
    }


def dashboard_tag(selection: ModuleSelection) -> bytes:
    """Stylesheet hiding panels of modules that are not installed.

    Empty when every module with panels is installed, so a legacy
    dashboard is byte-for-byte what it was.
    """
    selectors = [
        selector
        for module_id, owned in PANEL_SELECTORS.items()
        if module_id not in selection.installed
        for selector in owned
    ]
    if not selectors:
        return b""
    css = ",".join(selectors) + "{display:none!important}"
    hidden = json.dumps(
        sorted(m for m in PANEL_SELECTORS if m not in selection.installed)
    )
    return (
        MODULES_MARKER
        + b'\n<style data-truepanel-modules-hidden=\''
        + hidden.encode()
        + b"'>"
        + css.encode()
        + b"</style>\n"
    )
