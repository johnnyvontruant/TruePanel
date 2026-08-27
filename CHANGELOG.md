# Changelog

All notable TruePanel changes are recorded here.

TruePanel follows semantic versioning. Stable release tags use the form `vMAJOR.MINOR.PATCH`; release-candidate tags use `vMAJOR.MINOR.PATCH-rcN`.

## [Unreleased]

The post-1.2 development line extends TruePanel from health visibility into
guided, evidence-backed recovery and predictive reliability.

### Added

- Added Project Pathfinder's universal guided-recovery contract, durable
  recovery sessions, Recovery Command Deck, machine-verification state, and
  recovery timeline.
- Added Project Lifeline's fail-closed recovery handoff for
  replacement-worthy SMART evidence joined to verified storage identity.
- Added supported TrueNAS `POSTINIT` persistence for the `i2c-dev` module,
  with managed-task verification, uninstall ownership protection, and reboot
  validation on BattleStation.
- Added Project ORACLE adaptive baselines, trend and anomaly states,
  cross-signal correlation, Ghost Mode primitives, and slow-degradation
  HoloDeck scenarios.
- Added Project AEGIS as a read-only reliability layer with a universal
  Recovery Coverage Matrix, probable-cause correlation, request-independent
  predictive sampling, verification rehearsals, Black Box evidence capture,
  and a mobile-first Reliability view.
- Added a current Mission Control and reliability operating guide and refreshed
  the platform overview, architecture, documentation map, and roadmap.

### Changed

- Critical SMART findings now escalate into a storage-specific Lifeline path
  rather than stopping at a generic warning.
- Mission Control can present one probable shared cause while retaining every
  contributing component alert and its evidence.
- Recovery trust now requires a declared detector, complete guidance arc,
  fault-specific verifier, deterministic regression coverage, and a passed
  fault-present-to-recovered rehearsal.
- Documentation now distinguishes stable 1.2.0 behavior, accepted post-release
  changes, and capabilities that remain undeployed on the reference NAS.

### Safety

- Pathfinder, Lifeline, ORACLE, and AEGIS do not gain destructive storage or
  hardware-control authority.
- ORACLE statistical drift cannot invent a production hard fault.
- AEGIS correlation cannot hide or delete contributing alerts and remains
  explicitly read-only.
- TrueNAS boot persistence uses the supported Init/Shutdown Scripts middleware
  contract rather than generic appliance filesystem configuration.
- ORACLE baseline learning is bounded to one sample per telemetry interval and
  cannot be accelerated by dashboard request volume.
- SMART recovery remains fail-closed until critical SMART evidence is clear
  and the independently observed ZFS member state is explicitly `ONLINE`.

### Validated

- The supported `i2c-dev` POSTINIT task survived a full BattleStation reboot;
  the module and `/dev/i2c-0` returned automatically while both application
  services remained healthy and physical LCD buttons continued to work.
- The AEGIS shared-cooling HoloDeck scenario identified the probable shared
  cause 27 samples before the first isolated lab threshold, reduced two
  terminal alerts to one operator incident, passed recovery rehearsal, and
  preserved two privacy-sanitized Black Box frames.
- PR #78 passed formal review and authoritative GitHub Actions run 1116:
  2,348 tests passed, installed-wheel smoke passed, and regressions cover
  request-independent sampling plus SMART/ZFS recovery verification.
- The AEGIS increment was accepted into the post-1.2 development line without
  deployment or live hardware access.

## [1.2.0] - 2026-08-19

TruePanel 1.2.0 graduates the validated RC3 tree to a stable release and
adds Mission Control Preflight as the final operator-facing release feature.
The RC1 through RC3 history below preserves the detailed lifecycle,
Mission Control, HoloDeck, and Black Box development record.

### Added

- Added on-demand Mission Control Preflight reporting for Host, Storage,
  Cooling, Front Panel, and Safety Interlocks.
- Added READY / REVIEW / HOLD projection while preserving non-blocking
  review items instead of hiding them behind an overall ready state.
- Added a downloadable privacy-safe compatibility support bundle from
  Mission Control.

### Safety

- Preflight remains passive and read-only and does not grant hardware-control
  authority.
- Support bundles continue to exclude hostnames, IP addresses, hardware
  serials, WWIDs, MAC addresses, usernames, configuration secrets, and pool
  contents.
- Automatic thermal control remains deliberately unarmed.

### Validated

- The final Preflight integration passed 2,045 canonical tests on the
  reference development environment before stable promotion.
- Live BattleStation validation reported `READY` / `SUPPORTED` with 14 PASS,
  2 REVIEW, and 0 FAIL checks while both TruePanel services remained active.
- The live support-bundle endpoint returned HTTP 200, omitted the reference
  host's hostname and all detected non-loopback IP addresses, and emitted a
  single `Cache-Control: no-store` response header.
- Mission Control Preflight completed live visual and operator-flow review on
  the reference QNAP TVS-671.

## [1.2.0-rc3] - 2026-08-18

TruePanel 1.2.0 RC3 adds HoloDeck, a deterministic whole-stack digital
twin, and the Black Box incident toolchain to the validated RC2
lifecycle and Mission Control foundation.

### Added

- Added deterministic BattleStation host fixtures, scenario playback,
  bounded fault injection, invariant evaluation, and read-only Mission
  Control snapshots through HoloDeck.
- Added sanitized Black Box recording, deterministic replay, sessions,
  fault mutation, compatibility analysis, narration, and Mission
  Control adapters.
- Added the data-only Incident Compiler, which minimizes recordings into
  reproducible regression artifacts without generating executable code.
- Added a packaged `truepanel` console entry point and an installed-wheel
  smoke test that runs outside the source checkout.

### Changed

- Host construction and web snapshots now accept explicit simulated
  providers while production selection remains one-way and unchanged.
- HoloDeck imports are lazy so ordinary version, verification, LCD, and
  Mission Control commands do not load the simulation runtime.
- GitHub Actions now builds a wheel, installs it into a fresh environment,
  and exercises HoloDeck run, injection, checking, replay, and compilation.

### Safety

- Black Box replay is bounded to 10,000 nonblank frames, 64 MiB of total
  input, and 256 KiB per frame before decoding or materialization.
- HoloDeck clocks and scenario timestamps reject non-finite values;
  scenarios and command work are bounded before execution.
- HoloDeck rejects protected runtime paths and aliases beneath `/dev`,
  `/etc`, `/proc`, `/run`, `/sys`, and `/var`.
- Simulated Host Agent control uses in-memory ownership, status, and
  execution with no fan-command server or production hardware authority.

### Validated

- The combined RC2 and HoloDeck tree passed the canonical GitHub Actions
  test job and the installed-wheel smoke job.
- Local integration validation passed 2,033 canonical tests and 114
  release-critical and HoloDeck-focused tests.
- BattleStation passed 25 production-isolation contracts against the exact
  RC3 integration commit while both live service identities remained
  unchanged.
- The protected live deployment fingerprint remained identical across
  257 files before and after HoloDeck run, fault injection, invariant
  checking, replay, and incident compilation.

## [1.2.0-rc2] - 2026-08-17

TruePanel 1.2.0 RC2 combines the hardened lifecycle foundation from
RC1 with trustworthy network telemetry, read-only Health Intelligence,
a refined Virtual Front Panel, and a clearer Mission Control cockpit.

### Added

- Added passive per-interface network throughput telemetry using
  kernel RX/TX counters and monotonic sampling.
- Added friendly Ethernet Port and Tailscale identification across
  Mission Control and the physical LCD while preserving kernel
  interface names for diagnostics.
- Added conservative Health Intelligence for cooling, thermal,
  storage, network, front-panel, and TruePanel service state.
- Added cached, read-only observation of the LCD and Mission Control
  systemd services.
- Added a full-width System Health command layer with normalized
  subsystem states and honest unknown-state reporting.
- Added compact cooling instruments for temperature, active profile,
  recommendation, readiness, fan speed, and PWM state.

### Changed

- Refined the Virtual Front Panel with deeper blue, restrained
  dot-matrix texture, tighter spacing, and crisp white glyphs.
- Reorganized Mission Control around current operating condition and
  operator decisions.
- Moved commissioning, fan-control, and thermal history into a
  collapsed diagnostics drawer while keeping live controls visible.
- Guarded promotion now bootstraps the managed `bin/truepanel` CLI
  wrapper when upgrading legacy deployments that predate it.

### Safety

- Network, health, and service observation remain read-only.
- No endpoint, configuration write, hardware command, service action,
  or control authority was added.
- Automatic thermal control remains deliberately unarmed.

### Validated

- Network telemetry and Health Intelligence passed focused regression
  coverage and live BattleStation verification.
- Virtual LCD and cockpit changes passed complete GitHub Actions checks.
- Live cockpit visual QA found no clipping, duplicate identifiers,
  unintended advisories, or control regressions.

## [1.2.0-rc1] - 2026-08-13

- Harden guarded upgrade promotion so invalid backup paths are rejected before any backup copy begins; document the required sibling `.truepanel-backup-` naming contract.
- Preserve installer-owned `bin/` artifacts during stage promotion so `bin/truepanel` survives source synchronization while retained backups remain able to restore the wrapper.
- Run promotion and rollback verification with the deployed generation's own Python/runtime, retrying only transient Mission Control or LCD readiness failures.

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
