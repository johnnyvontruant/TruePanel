# Changelog

All notable TruePanel changes are recorded here.

TruePanel follows semantic versioning. Release tags use the form `vMAJOR.MINOR.PATCH`.

## [1.0.0]

TruePanel 1.0.0 is the first stable release of the independent TruePanel platform.

### Flight Deck

- Production dashboard rotation with startup diagnostics, transitions, night mode, and idle behavior.
- Native character-ROM instruments, trends, progress indicators, and display-safe formatting.
- Centered server identity, network address, performance, storage, thermal, activity, and mission-status pages.
- Button-driven navigation through the A125 front-panel controller.

### Mission Control

- Priority-aware events, alert history, duplicate suppression, interruption policy, and recovery handling.
- Storage, SMART, thermal, pool, ZFS activity, and healthy-state watchers.
- Audible alert support and storage-specific alert rendering.
- Automatic routing of storage failures to the corresponding physical drive-bay indicator.

### Hardware platform

- Verified A125 communication on `/dev/ttyS1` at 1200 baud.
- Transaction ownership, response validation, timing evidence, and guarded laboratory access.
- TVS-671 enclosure inventory, storage topology, SMART telemetry, and command-center tooling.
- Verified six-bay identify LED control through `/dev/i2c-0` at SMBus address `0x33`.
- TrueNAS-safe systemd installation under `/opt/truepanel`.

### Platform services

- Plugin API v1 with isolation, administration commands, examples, and capability registration.
- Persistent historical telemetry and LCD history views.
- Theme packs, simulation scenarios, diagnostics, hardware inspection, and release-grade CLI commands.
- Project Stargate safety policy, authorization interlocks, evidence capture, protocol simulation, and reusable laboratory tooling.

### Repository and documentation

- Consolidated `main` and `develop` while preserving the complete project history.
- Removed generated artifacts, runtime state, stale backups, and obsolete root utilities.
- Added architecture, installation, hardware, CLI, Stargate, upgrade, contribution, security, and release documentation.
- Added a release contract that prevents prerelease version drift and missing release files.

### Compatibility

The reference platform for 1.0.0 is:

- TrueNAS SCALE 25.10
- Python 3.11
- QNAP TVS-671
- A125 front-panel controller
- Six internal SATA drive bays

Other compatible QNAP systems may work, but hardware writes must remain model-verified.

## Earlier milestones

The earlier `v0.7.0`, `v0.8.0-core`, `v0.9.0`, and `v1.0.0-rc0` tags preserve the development milestones that led to the stable platform.

### Fixed

- Primary LCD pages now rotate every five seconds, with a 120-second backlight timeout long enough to show a complete Flight Deck cycle.

- Persistent alert checks can no longer bypass normal menu advancement and stall the LCD on one page.

- Mission Control, Event Queue, and Alert History diagnostic views no longer occupy the primary LCD rotation; a persistent incident interrupts once and then returns immediately to normal Flight Deck pages.

- Left and right hardware buttons now always escape Event Queue and Alert History pages instead of redrawing a single entry indefinitely.

- Alert interruptions are latched per incident, preventing transient healthy samples or alternating warnings from repeatedly taking over Flight Deck.

- Persistent unchanged alerts interrupt once, then remain visible through normal Flight Deck status, SMART, queue, and history rotation.
