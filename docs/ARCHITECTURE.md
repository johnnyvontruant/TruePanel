# TruePanel Architecture

## Design goal

TruePanel converts otherwise dormant appliance hardware into a calm, testable, hardware-aware operations console. The system separates collection, decisions, presentation, persistence, and physical control so each layer can evolve without turning the runtime into a single giant script.

## Runtime path

```text
truepanel.py
  -> truepanel.cli
      -> lcd-menu.py
          -> collector.py
          -> Mission Control
          -> Display Manager
          -> AutoPilot
          -> A125 LCD driver
```

The installed service launches `/opt/truepanel/bin/truepanel run`.

## Core layers

### Collection

`TruePanelCollector` gathers CPU, memory, networking, pools, temperatures, ARC, ZFS activity, and SMART state. Hardware services add enclosure topology, inventory, health, and telemetry.

Collectors produce shared state. They do not decide how that state should interrupt the display.

### Mission Control

Mission Control evaluates watchers and produces structured `MissionEvent` objects. Events carry priority, category, source, stable identifiers, messages, and metadata.

Storage events include physical bay, device, serial, model, transition type, health state, SMART counters, and temperature when available.

### Watchers

Watchers translate state changes into events. Important watcher families include:

- pool health
- thermal state
- ZFS operations
- SMART state
- structured storage health
- healthy fallback

The storage watcher can notify observers before Mission Control selects the highest-priority event. This allows hardware indicators to react to every bay transition.

### Alert policy

`AlertManager` tracks alert lifecycle, duplicate suppression, history, interruption policy, acknowledgement, and recovery.

Drive-specific storage faults are deliberately not rendered as redundant LCD interrupt pages. They remain structured events, update the physical bay LED, and appear on the rotating storage detail page. System-wide and pool-wide alerts may still interrupt.

### Display Manager

`DisplayManager` converts system state and events into `DisplayFrame` objects. It owns dashboard selection, text fitting, native graphics, priorities, timeouts, transitions, and alert detail routing.

The Flight Deck includes pages for system identity, CPU and memory, pools, capacity, thermal state, networking, ZFS activity, storage faults, and plugin-provided pages.

### AutoPilot

AutoPilot schedules page rotation, honors user button activity, slows rotation when idle, applies night mode, and delegates frame creation to the Display Manager.

### Display stack

The display stack supports:

- 16x2 text frames
- A125 native ROM characters
- custom CGRAM glyphs
- instrument widgets
- gauges and trends
- startup sequences
- themes
- direct button-driven pages

### Hardware Manager

`HardwareManager` lazily constructs and caches hardware controllers. Current providers include:

- A125 LCD controller
- buzzer
- enclosure controller
- storage inventory
- topology
- SMART provider
- health service
- bay LED controller

Lazy construction prevents unused hardware paths from being opened during tests or unrelated commands.

### Storage bay indicators

On the TVS-671, `TVS671BayLedController` sends verified SMBus Write Byte commands to `/dev/i2c-0` at address `0x33`.

`StorageBayIndicator` observes structured storage events:

```text
warning or critical bay fault -> identify LED on
recovered or healthy bay       -> identify LED off
```

The controller suppresses duplicate writes and tracks multiple active bays independently.

### Historical telemetry

The history subsystem records selected system state at configured intervals. Stored series feed trend widgets, diagnostics, and later analysis without requiring the display refresh interval to become the persistence interval.

### Plugins

The plugin manager isolates external extensions from the core runtime. Plugins may provide collectors, dashboard pages, watchers, notifications, themes, or other registered capabilities. Runtime plugin state is local and intentionally excluded from Git.

### Project Stargate

Project Stargate is the experimental layer used to characterize undocumented hardware. It includes catalogs, classifiers, execution modes, danger levels, authorization phrases, session records, captures, repeatability tests, fingerprints, timing experiments, and capability providers.

The production hardware layer receives only commands that graduate from Stargate with reproducible evidence.

## Failure containment

TruePanel favors degraded operation over runtime collapse:

- collector failures return conservative defaults;
- watcher observer failures are logged and contained;
- plugins are isolated;
- hardware providers are lazy;
- duplicate hardware writes are suppressed;
- experimental commands require explicit interlocks;
- the service restarts through systemd.

## Testing

The test suite covers protocol framing, transport ownership, hardware managers, widgets, dashboards, telemetry, storage health, bay LEDs, ZFS operations, plugins, Project Stargate policies, and integration seams.

At the July 19, 2026 platform consolidation, the complete suite passed 861 tests.

## Mission Control service boundary

Mission Control is a companion process rather than part of the LCD runtime.

```text
Browser
   |
   v
truepanel-mission-control.service
   |
   +--> telemetry snapshots
   +--> history and capability APIs
   +--> validated configuration policy
   +--> atomic YAML persistence when explicitly enabled

truepanel.service
   |
   +--> collectors
   +--> Mission Control event policy
   +--> Flight Deck rendering
   +--> LCD buttons, buzzer, and approved hardware adapters
```

The web service may read shared TruePanel state and configuration, but HTTP handlers do not directly operate serial, I2C, sysfs, LEDs, fans, buttons, or the buzzer.

Configuration persistence is guarded by all of these boundaries:

1. Writes are disabled by default at service startup.
2. Only supported Night Mode fields are accepted.
3. Policy validation rejects unsafe alert suppression.
4. Files are replaced atomically.
5. A timestamped backup is created before replacement.
6. The primary LCD service is not automatically restarted.

This separation allows web development and service restarts without interrupting the Flight Deck.
