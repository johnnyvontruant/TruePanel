"""The TruePanel module catalog.

One entry per installable feature. The terminal installer, the
``truepanel modules`` CLI and the Mission Control Modules page all read
this list, so a feature's description, requirements and "what it adds"
text is written exactly once, here.

Removing a module *unhooks* it: its services, LCD pages, Mission Control
panels and API routes stop loading. Its code stays on disk so upgrades,
rollback and shared imports keep working. See docs/MODULES.md.

Catalog rules:

* ``id`` values are permanent. They are stored in truepanel.yaml.
* Bump a module's ``version`` when what it adds or requires changes,
  and record the change in CHANGELOG.md.
* ``requires`` may only name other catalog modules. Outside needs
  (Sonarr, a USB drive, verified hardware) go in ``needs`` as plain text.
* Core modules cannot be removed and may not require optional ones.
"""

from __future__ import annotations

from dataclasses import dataclass, field

CORE = "core"
RECOMMENDED = "recommended"
OPTIONAL = "optional"
DEVELOPER = "developer"

TIERS = (CORE, RECOMMENDED, OPTIONAL, DEVELOPER)

TIER_LABELS = {
    CORE: "Core",
    RECOMMENDED: "Recommended",
    OPTIONAL: "Optional",
    DEVELOPER: "Developer",
}


@dataclass(frozen=True)
class Module:
    id: str
    name: str
    tier: str
    version: str
    summary: str
    description: str
    adds: tuple[str, ...] = ()
    requires: tuple[str, ...] = ()
    needs: tuple[str, ...] = ()
    # Code areas that belong to this module, for maintainers.
    packages: tuple[str, ...] = ()
    # Existing truepanel.yaml switches this module governs. A feature
    # runs only when its module is installed AND its own switch is on.
    config_keys: tuple[str, ...] = field(default=())

    @property
    def removable(self) -> bool:
        return self.tier != CORE

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "tier": self.tier,
            "tier_label": TIER_LABELS[self.tier],
            "version": self.version,
            "summary": self.summary,
            "description": self.description,
            "adds": list(self.adds),
            "requires": list(self.requires),
            "needs": list(self.needs),
            "packages": list(self.packages),
            "config_keys": list(self.config_keys),
            "removable": self.removable,
        }


CATALOG: tuple[Module, ...] = (
    # ------------------------------------------------------------ core
    Module(
        id="flight_deck",
        name="LCD Flight Deck",
        tier=CORE,
        version="1.0.0",
        summary="The front-panel LCD and its buttons.",
        description=(
            "Brings the NAS front panel back to life: rotating system, "
            "storage, network and thermal pages on the 16x2 LCD, button "
            "navigation, startup diagnostics, themes and night mode."
        ),
        adds=(
            "LCD pages: home, storage, capacity, network, thermal, ZFS",
            "Front-panel button navigation",
            "Startup screens, themes and night mode",
        ),
        packages=("display", "flightdeck", "pages", "menu", "themes", "qnaplcd"),
        config_keys=("flightdeck", "theme", "theme_pack", "graphics_engine"),
    ),
    Module(
        id="mission_control",
        name="Mission Control",
        tier=CORE,
        version="1.0.0",
        summary="The browser cockpit on port 8787.",
        description=(
            "The web dashboard: live CPU, memory, network, storage, fan "
            "and service state, Pilot and Flight Engineer modes, the "
            "Flightdeck skin and a virtual front panel that works like "
            "the real buttons."
        ),
        adds=(
            "Web dashboard at http://<nas>:8787",
            "Virtual front panel",
            "Day/Night lighting and the Flightdeck skin",
        ),
        packages=("web", "mission_control", "collectors", "watchers", "host"),
        config_keys=("mission_control",),
    ),
    Module(
        id="health",
        name="Health & Fault View",
        tier=CORE,
        version="1.0.0",
        summary="Tells you what's wrong, what it affects and how to fix it.",
        description=(
            "Watches cooling, temperatures, storage, network, the front "
            "panel and services. When something fails it shows one plain "
            "headline, what it affects, what is protecting you, and a "
            "step-by-step Flight Manual checklist."
        ),
        adds=(
            "Status lights and Master WARNING / CAUTION",
            "Friendly fault view with a guided checklist",
            "Storage and fan health alerts",
        ),
        packages=("health", "guidance"),
        config_keys=(
            "mission_control.storage_health",
            "mission_control.fan_health",
        ),
    ),
    Module(
        id="history",
        name="Telemetry History",
        tier=CORE,
        version="1.0.0",
        summary="Keeps 30 days of readings so trends and faults have evidence.",
        description=(
            "Records one sample a minute of CPU, memory, temperature, "
            "capacity, network and ZFS activity. Other features use it to "
            "show trends and back up their findings."
        ),
        adds=("Trend data for Mission Control and other modules",),
        packages=("history",),
        config_keys=("history",),
    ),
    Module(
        id="flight_recorder",
        name="Flight Recorder",
        tier=CORE,
        version="1.0.0",
        summary="A readable log of alerts and actions.",
        description=(
            "Writes new alerts, buzzer activations and other events to "
            "/var/lib/truepanel/logs/flight.log. If writing fails, alerts "
            "still go out. Useful when asking for help."
        ),
        adds=("Flight Logs overlay in Mission Control",),
        packages=("flight_recorder", "flight_logs"),
    ),
    Module(
        id="lifecycle",
        name="Install & Maintenance Tools",
        tier=CORE,
        version="1.0.0",
        summary="Compatibility check, doctor, upgrade, rollback and repair.",
        description=(
            "The tools that install, check, upgrade, roll back, repair and "
            "uninstall TruePanel. The module installer itself depends on "
            "them."
        ),
        adds=(
            "truepanel compatibility / doctor / verify",
            "truepanel upgrade / repair",
        ),
        packages=(
            "compatibility",
            "doctor",
            "verify",
            "upgrade",
            "repair",
            "lifecycle",
            "config",
            "modules",
        ),
    ),
    # ----------------------------------------------------- recommended
    Module(
        id="hardware_control",
        name="Hardware Control",
        tier=RECOMMENDED,
        version="1.0.0",
        summary="Fan profiles, drive-bay lights and the buzzer.",
        description=(
            "Lets TruePanel drive the chassis fans (Quiet to Afterburners), "
            "light the drive-bay LEDs to point at a problem drive, and "
            "sound the buzzer on alerts. Each control stays locked until "
            "it has been verified on this model."
        ),
        adds=(
            "Fan profile controls in Mission Control",
            "Bay LED fault and identify lights",
            "Buzzer tones for warnings and critical alerts",
        ),
        needs=("Hardware that passes the compatibility check",),
        packages=("hardware",),
        config_keys=(
            "hardware.fan_control",
            "hardware.thermal_policy",
            "buzzer",
            "mission_control.storage_health.bay_leds_enabled",
        ),
    ),
    Module(
        id="guided_recovery",
        name="Guided Recovery",
        tier=RECOMMENDED,
        version="1.0.0",
        summary="Walks you through fixing a fault and checks that it worked.",
        description=(
            "Pathfinder tracks each fault from detection through repair "
            "and verification. Lifeline adds careful, step-by-step "
            "handling when a drive needs replacing."
        ),
        adds=(
            "Recovery sessions that remember where you are",
            "Drive replacement workflow with bay identification",
        ),
        packages=("guidance.sessions", "lifeline"),
    ),
    Module(
        id="oracle",
        name="Drift Detection (ORACLE)",
        tier=RECOMMENDED,
        version="1.0.0",
        summary="Learns what normal looks like and flags slow changes.",
        description=(
            "Builds a baseline for temperatures, fan speeds and other "
            "readings and points out readings that are drifting away from "
            "normal before they become faults."
        ),
        adds=("Developing-fault notes in Mission Control",),
        packages=("oracle",),
    ),
    Module(
        id="reliability",
        name="Reliability Intelligence",
        tier=RECOMMENDED,
        version="1.0.0",
        summary="Connects related alerts into one probable cause.",
        description=(
            "AEGIS links alerts that share a cause (for example a fan "
            "failure and rising drive temperatures), and the SENTINEL "
            "Flight Director explains what each fault affects. It only "
            "reads; it never controls hardware."
        ),
        adds=(
            "Probable-cause view (AEGIS / Checkride)",
            "Flight Director impact explanations",
            "Watchtower view",
        ),
        requires=("oracle",),
        packages=("aegis", "sentinel"),
    ),
    Module(
        id="lcd_history",
        name="LCD History Pages",
        tier=RECOMMENDED,
        version="1.0.0",
        summary="Trend graphs on the front-panel LCD.",
        description=(
            "Adds small history graphs for CPU, memory, temperature, "
            "capacity, network, ZFS and alerts to the LCD rotation."
        ),
        adds=("LCD pages: history-cpu, history-ram, history-temperature and more",),
        packages=("history.lcd",),
        config_keys=("history.lcd",),
    ),
    Module(
        id="observatory",
        name="Current Activity (OBSERVATORY)",
        tier=RECOMMENDED,
        version="1.0.0",
        summary="Shows what the NAS is busy doing right now.",
        description=(
            "Shows current activity such as scrubs, resilvers and heavy "
            "disk or network use, and says plainly when it's idle."
        ),
        adds=("CURRENT ACTIVITY panel in Mission Control",),
        packages=("activity",),
    ),
    # -------------------------------------------------------- optional
    Module(
        id="cargo_bay",
        name="Cargo Bay",
        tier=OPTIONAL,
        version="1.0.0",
        summary="Recent Sonarr and Radarr arrivals.",
        description=(
            "Shows new TV episodes and movies as Sonarr and Radarr bring "
            "them in, and whether each one has a backup copy."
        ),
        adds=("Cargo Bay panel in Mission Control",),
        needs=("Sonarr and/or Radarr running on the NAS",),
        packages=("cargo",),
        config_keys=("mission_control.cargo_bay",),
    ),
    Module(
        id="loadmaster",
        name="Loadmaster",
        tier=OPTIONAL,
        version="1.0.0",
        summary="Keeps USB drives in sync with NAS folders at the press of Copy.",
        description=(
            "Plug in a labelled USB drive, press Copy on the front panel, "
            "and Loadmaster copies new files in either direction, checks "
            "every copy, and holds anything unclear for you to review."
        ),
        adds=(
            "Copy-button sync with LCD progress screens",
            "Loadmaster panel in Mission Control",
        ),
        requires=("cargo_bay",),
        needs=(
            "USB drives labelled to match NAS folders",
            "A front-panel Copy button",
        ),
        packages=("loadmaster",),
        config_keys=("loadmaster",),
    ),
    Module(
        id="vpn_status",
        name="VPN Status",
        tier=OPTIONAL,
        version="1.0.0",
        summary="Shows whether Tailscale is connected.",
        description=(
            "Adds Tailscale connection state to Mission Control's network "
            "readout, so you can see remote access is up."
        ),
        adds=("VPN state in the network panel",),
        needs=("Tailscale installed on the NAS",),
        packages=("vpn_status",),
    ),
    # ------------------------------------------------------- developer
    Module(
        id="stargate_lab",
        name="Stargate Lab",
        tier=DEVELOPER,
        version="1.0.0",
        summary="LCD controller protocol experiments.",
        description=(
            "Tools for probing and commissioning new LCD controllers and "
            "hardware. Not needed for everyday use."
        ),
        adds=("truepanel lab commands",),
        packages=("lab", "diagnostics"),
    ),
    Module(
        id="holodeck",
        name="HoloDeck & Black Box",
        tier=DEVELOPER,
        version="1.0.0",
        summary="Digital twin, fault rehearsal and replay.",
        description=(
            "A simulated copy of the whole system for rehearsing failures, "
            "plus Black Box recording and the Incident Compiler that turns "
            "real failures into test cases."
        ),
        adds=("truepanel holodeck commands", "Black Box recording and replay"),
        packages=("holodeck", "history.black_box"),
    ),
    Module(
        id="hangar",
        name="Hangar & Layout Studies",
        tier=DEVELOPER,
        version="1.0.0",
        summary="Experiment tracking and dashboard layout studies.",
        description=(
            "Project HANGAR experiment records and the Glass Cockpit "
            "layout study used while designing Mission Control."
        ),
        adds=("python -m truepanel.hangar",),
        packages=("hangar", "glass_cockpit"),
    ),
)

MODULES: dict[str, Module] = {module.id: module for module in CATALOG}


def get_module(module_id: str) -> Module:
    try:
        return MODULES[module_id]
    except KeyError:
        raise KeyError(f"Unknown TruePanel module: {module_id}") from None


def modules_in_tier(tier: str) -> tuple[Module, ...]:
    return tuple(module for module in CATALOG if module.tier == tier)


def validate_catalog() -> list[str]:
    """Return a list of catalog problems; empty means healthy."""
    problems: list[str] = []
    seen: set[str] = set()
    for module in CATALOG:
        if module.id in seen:
            problems.append(f"duplicate id: {module.id}")
        seen.add(module.id)
        if module.tier not in TIERS:
            problems.append(f"{module.id}: unknown tier {module.tier!r}")
        if not module.summary or not module.description:
            problems.append(f"{module.id}: missing summary or description")
        for required in module.requires:
            if required not in MODULES:
                problems.append(f"{module.id}: requires unknown {required}")
            elif module.tier == CORE and MODULES[required].tier != CORE:
                problems.append(
                    f"{module.id}: core module requires optional {required}"
                )
    return problems
