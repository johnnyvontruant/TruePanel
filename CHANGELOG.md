# Changelog

All notable TruePanel changes are recorded here.

TruePanel follows semantic versioning. Stable release tags use the form `vMAJOR.MINOR.PATCH`; release-candidate tags use `vMAJOR.MINOR.PATCH-rcN`.

## [1.2.0-rc1] - 2026-08-13

- Harden guarded upgrade promotion so invalid backup paths are rejected before any backup copy begins; document the required sibling `.truepanel-backup-` naming contract.

TruePanel 1.2.0 RC1 graduates the hardened native lifecycle,
compatibility survey, Host ownership boundary, and clean-install path.

### Added

- Guarded install, uninstall, upgrade, repair, verify, rollback,
  cleanup, and promotion lifecycle contracts.
- Passive compatibility survey, storage classification, and
  privacy-safe support bundles.
- Dormant privileged Host Agent deployment with single-owner
  enforcement, readiness, fan-safety, acceptance, and cutover checks.
- Clean-install Run 3 regression and release evidence.

### Changed

- Fresh-install synchronization excludes source-local configuration,
  secrets, virtual environments, caches, history, and plugin state.
- Clean-install state can be quarantined outside the managed target.
- Support evidence is retained outside the managed installation root.
- Isolated TrueNAS virtual-environment bootstrap supports systems
  without `ensurepip`.
- Fresh buzzer defaults are safe and use the supported `pcspkr`
  backend while disabled.

### Validated

Clean-install Run 3 on the reference QNAP TVS-671 passed:

- genuine blank-target installation;
- first LCD hardware startup;
- Mission Control activation;
- automatic Flight Deck rotation;
- physical front-panel button navigation;
- controlled LCD-service restart;
- full TrueNAS reboot;
- native installed verification;
- motherboard fan control remaining Automatic;
- Host acceptance remaining PASS;
- standalone Host Agent remaining dormant and marker-gated.

Unsupported fresh-buzzer warnings fell from five pre-fix occurrences
to zero on corrected fresh startup, controlled restart, full reboot,
and final post-reboot physical validation.

## [1.1.0] - 2026-07-30

TruePanel 1.1.0 expands the platform with guarded cooling control,
thermal-policy observation, improved fan telemetry, startup effects,
and a complete visual documentation refresh.

### Cooling and fan control

- Added guarded manual fan profiles with command-socket isolation.
- Added automatic restoration, dead-man expiry, and safety recovery.
- Added configurable quiet, balanced, cooling boost, and Afterburners profiles.
- Added fan RPM, PWM, profile, authority, and safety-hold telemetry.
- Added calibrated fan gauges and corrected live dashboard rendering.
- Added fan-control history and recovery transition recording.
- Added simulation drills and calibration laboratory tools.
- Added persistent Fintek `f71882fg` driver loading for the TVS-671 reference deployment.

### Thermal policy

- Added observe-only thermal recommendations.
- Added recommendation history and alignment reporting.
- Added automatic-control readiness checks with explicit blockers.
- Added a deliberately unarmed automatic-control contract.
- Added dashboard visibility for thermal policy state and readiness.

### Flight Deck and hardware

- Added fan RPM, PWM, and safety status pages.
- Added red-to-green drive-bay startup animation.
- Improved LCD startup timing and graceful shutdown behavior.
- Fixed the QNAP LCD reader shutdown race.
- Improved fan inventory discovery and channel labeling.

### Mission Control

- Added guarded fan profile controls.
- Added cooling readiness and thermal policy panels.
- Added visible calibrated fan RPM gauges.
- Added operational fan-control history and safety state.

### Documentation and branding

- Added a new TruePanel logo.
- Added LCD Flight Deck renderings.
- Added Mission Control screenshots.
- Added an architecture diagram.
- Updated installation guidance for the TrueNAS POSTINIT deployment.
- Documented the Fintek driver, runtime paths, and production verification contract.

### Compatibility

The reference platform for 1.1.0 is:

- TrueNAS SCALE 25.10.5
- Python 3.11
- QNAP TVS-671
- A125 front-panel controller
- Fintek F71869A hardware monitor
- Six internal SATA drive bays
- Two verified chassis fan-control channels

Other QNAP systems remain unverified until their controller paths,
telemetry, and command maps are reproduced safely.

## [1.0.0]

- Added a hardened Mission Control web companion service with read-only defaults, guarded Night Mode persistence, LAN deployment controls, and operator CLI commands.

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
