# TruePanel Modules

TruePanel 2.0 splits its features into **modules**. You install the core and
add only the features that fit your NAS. Every module is described in one
place, `truepanel/modules/catalog.py`. The terminal installer, the
`truepanel modules` command and the Mission Control Modules page all read
from that file.

> **Status (2.0 in progress):** this release adds the catalog and the
> read-only `truepanel modules` commands. Turning features on and off,
> the installer menu and the Mission Control Modules page come in the
> next 2.0 pull requests. Nothing changes on an existing install yet.

## Quick reference: How To

| I want to… | Do this |
| --- | --- |
| See every module and whether it's installed | `truepanel modules list` |
| Include developer tools in the list | `truepanel modules list --developer` |
| Read what one module does and needs | `truepanel modules show loadmaster` |
| Get the list as JSON | `truepanel modules list --json` |
| Check the catalog itself is healthy | `truepanel modules validate` |
| Read a different config file | `truepanel modules --config /path/truepanel.yaml list` |

Run these from the TruePanel install folder, the same way as other
`truepanel` commands.

## Tiers

| Tier | Meaning |
| --- | --- |
| **Core** | Always installed. Can't be removed. |
| **Recommended** | On in the Recommended preset. Suits most QNAP-on-TrueNAS systems. |
| **Optional** | Off unless you choose it. Usually needs something outside TruePanel (Sonarr, USB drives, Tailscale). |
| **Developer** | Hidden unless you ask. Tools for building and testing TruePanel. |

## The modules

### Core

| Module | What it gives you |
| --- | --- |
| `flight_deck`: LCD Flight Deck | The front-panel LCD, its buttons, startup screens, themes and night mode |
| `mission_control`: Mission Control | The browser cockpit on port 8787 and the virtual front panel |
| `health`: Health & Fault View | Status lights, Master WARNING / CAUTION, and the plain fault view with a guided checklist |
| `history`: Telemetry History | 30 days of readings that other features use as evidence |
| `flight_recorder`: Flight Recorder | A readable log of alerts and actions |
| `lifecycle`: Install & Maintenance Tools | Compatibility check, doctor, verify, upgrade, rollback, repair |

### Recommended

| Module | What it gives you | Requires |
| --- | --- | --- |
| `hardware_control`: Hardware Control | Fan profiles, drive-bay LEDs, buzzer (each locked until verified on your model) | |
| `guided_recovery`: Guided Recovery | Pathfinder recovery sessions and Lifeline drive-replacement workflow | |
| `oracle`: Drift Detection | Learns normal readings and flags slow drift | |
| `reliability`: Reliability Intelligence | AEGIS probable cause, SENTINEL Flight Director, Watchtower | `oracle` |
| `lcd_history`: LCD History Pages | Trend graphs on the LCD | |
| `observatory`: Current Activity | What the NAS is busy doing right now | |

### Optional

| Module | What it gives you | Requires | Needs |
| --- | --- | --- | --- |
| `cargo_bay`: Cargo Bay | Recent Sonarr/Radarr arrivals and backup status | | Sonarr and/or Radarr |
| `loadmaster`: Loadmaster | Copy-button USB drive sync | `cargo_bay` | Labelled USB drives, a Copy button |
| `vpn_status`: VPN Status | Tailscale connection state | | Tailscale |

### Developer

`stargate_lab` (LCD protocol experiments), `holodeck` (digital twin, Black Box,
Incident Compiler), `hangar` (experiment records and layout studies).

## Presets

| Preset | Installs |
| --- | --- |
| `essentials` | Core only |
| `recommended` | Core + Recommended |
| `everything` | Core + Recommended + Optional (no developer tools) |

## How it's recorded

The installed list lives in `truepanel.yaml`:

```yaml
modules:
  installed:
    - hardware_control
    - guided_recovery
    - oracle
    - reliability
    - cargo_bay
    - loadmaster
```

- **Core modules** don't need listing. They're always installed.
- **Requirements are added for you.** List `loadmaster` and `cargo_bay` comes
  with it, and `truepanel modules list` says why.
- **Misspelled or unknown names** are reported and ignored. They never stop
  TruePanel.
- **No `modules:` section** means a configuration from before modules
  existed. Every feature stays installed, so upgrading to 2.0 changes nothing
  until you choose. An empty list (`installed: []`) means core only.

## What "remove" means

Removing a module **unhooks** it: its services, LCD pages, Mission Control
panels and API routes stop loading. Its code stays on disk. That keeps
upgrades, rollback and shared code working, and putting it back is
instant. Its saved data is kept unless you ask for it to be purged, and
purging always makes a backup first.

A module runs only when it is installed **and** its own setting is on (for
example `loadmaster.enabled`). Existing settings keep working the same way.

## For maintainers

- `id` values are permanent; they're stored in people's config files.
- Bump a module's `version` when what it adds or requires changes, and note
  it in `CHANGELOG.md`.
- `requires` may only name other modules. Outside needs go in `needs` as
  plain text, so the installer and Modules page can show them.
- Core modules can't require optional ones. `truepanel modules validate`
  and the test suite enforce this.
- `packages` and `config_keys` record which code and settings belong to each
  module, so whoever maintains TruePanel next can trace them.
