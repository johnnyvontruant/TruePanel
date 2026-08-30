# TruePanel Architecture

## Design goal

TruePanel converts otherwise dormant appliance hardware into a calm, testable, hardware-aware operations console. Collection, detection, interpretation, recovery, presentation, persistence, and physical control remain separate so each layer can evolve without silently inheriting authority from another.

The central architectural rule is:

> Evidence may flow upward into better explanations; control authority never flows upward by implication.

## Runtime boundaries

TruePanel currently has two active application processes and one dormant future process boundary.

```text
truepanel.service
  -> truepanel CLI
  -> LCD runtime
  -> collectors and embedded Host boundary
  -> watchers and alert policy
  -> Display Manager and AutoPilot
  -> A125 LCD and commissioned hardware adapters

truepanel-mission-control.service
  -> snapshot and history providers
  -> Health Intelligence
  -> Pathfinder recovery state
  -> AEGIS reliability view on development builds
  -> browser API and static dashboard

truepanel-host-agent.service
  -> installed but dormant
  -> marker-gated
  -> no normal embedded-runtime authority
```

The installed LCD service launches `/mnt/POOL/DATASET/TruePanel/bin/truepanel run`.

Mission Control is independently restartable. HTTP handlers do not directly operate serial, I2C, fan sysfs, bay LEDs, storage, the buzzer, or network configuration. Validated configuration writes remain disabled by default. Files are replaced atomically, and a timestamped backup is created before replacement. The primary LCD service is not automatically restarted.

## State flow

```text
TrueNAS and hardware providers
        |
        v
normalized snapshot
        |
        +--> LCD Flight Deck
        +--> Mission Control telemetry
        +--> Watchers and Health Intelligence
                    |
                    v
              structured findings
                    |
        +-----------+-----------+
        |                       |
        v                       v
Pathfinder recovery        ORACLE drift analysis
        |                       |
        +-----------+-----------+
                    |
                    v
          AEGIS incident hypothesis
                    |
        +-----------+-----------+
        |                       |
        v                       v
Mission Control view       HoloDeck rehearsal
                                |
                                v
                         Black Box evidence
```

This is a data and decision flow, not an actuator chain. AEGIS, Pathfinder, ORACLE, HoloDeck, and Black Box do not acquire hardware-control authority through composition.

## Core layers

### Collection

`TruePanelCollector` gathers CPU, memory, networking, pools, temperatures, ARC, ZFS activity, and SMART state. Host and hardware services add enclosure topology, inventory, physical-bay identity, health, fan state, front-panel state, and service evidence.

Collectors normalize observations. They do not decide display priority, fault severity, or recovery.

### Watchers and events

Watchers translate explicit state transitions into structured `MissionEvent` objects. Important families include:

- pool health;
- thermal state;
- fan health;
- SMART and storage health;
- ZFS operations;
- network state;
- front-panel availability;
- telemetry freshness;
- service health.

Events carry stable identifiers, priority, category, source, message, and evidence metadata. Storage events may include pool, vdev, device, physical bay, model, transition type, health state, SMART counters, and temperature.

### Alert policy

`AlertManager` owns duplicate suppression, interruption policy, acknowledgement, history, and recovery lifecycle.

Correlation never deletes the original alert. Drive-specific faults remain visible in structured state and storage detail even when Mission Control presents a consolidated higher-level incident.

### Health Intelligence

Health Intelligence converts normalized state into conservative operator findings. Unknown evidence remains unknown. It attaches stable guidance codes and the evidence required by the recovery layer.

### Pathfinder

Pathfinder owns stateful guided recovery:

```text
detection -> diagnosis -> guarded action -> verification -> resolution
```

Its recovery contract includes immediate stabilization, diagnosis, corrective guidance, verification criteria, action gates, and preserved session history.

A finding is not considered resolved merely because presentation changed. The fault-specific verifier must evaluate recovered subsystem evidence.

### Lifeline

Lifeline extends Pathfinder for critical physical-media evidence. It joins SMART findings to verified ZFS and physical-bay identity and fails closed when ownership is ambiguous.

Lifeline guides and verifies; it does not perform destructive pool operations or authorize blind disk removal.

### ORACLE

ORACLE maintains adaptive baselines, trend and anomaly state, and cross-signal correlations. Its predictive states identify developing behavior before a conventional threshold may fire.

Baseline learning is request-independent: status handlers reuse a thread-safe cached outlook and admit at most one predictive sample per telemetry interval. Independently verified alerts can still update incident correlation immediately between predictive samples.

ORACLE does not invent hard-fault authority. Statistical drift remains a hypothesis until supported by an independent detector.

### AEGIS

AEGIS is the read-only reliability-intelligence layer. It combines related ORACLE signals and verified alerts into one probable root-cause hypothesis with explicit confidence and supporting evidence.

Correlation is supplied through a TruePanel-owned policy interface. The
default declarative policy adapts Alertmanager-style grouping and inhibition
semantics without importing third-party runtime code: rules require distinct
evidence groups, carry explicit confidence weights and a HoloDeck verification
scenario, and may consolidate downstream symptoms while retaining every raw
alert. The policy contract is independently replaceable and CI-validated.

AEGIS:

- retains every contributing alert;
- uses “likely cause” and “hypothesis” semantics;
- surfaces the safest next action from existing guidance;
- exposes Pathfinder verification state;
- reports Recovery Coverage Matrix gaps;
- has no control-authority path.

The accepted shared-cooling experiment identifies one correlated incident 27 samples before the first isolated lab threshold and reduces two terminal alerts to one operator incident. The AEGIS development increment remains undeployed on the reference NAS.

### Recovery Coverage Matrix

A guidance path is `TRUSTED` only when it has:

- a declared detector;
- diagnostic evidence;
- immediate, diagnostic, corrective, and verification guidance;
- a fault-specific automated verifier;
- deterministic regression coverage;
- a passed fault-present-to-recovered rehearsal.

The test contract fails CI when a new actionable guidance code ships without that complete arc.

### HoloDeck

HoloDeck is the deterministic, hardware-isolated Digital Twin. It composes real TruePanel health, recovery, and presentation code with simulated host providers and a deny-all actuator boundary.

It supports bounded scenario playback, fault injection, invariant checks, Black Box replay, and data-only incident compilation. Protected runtime paths and production hardware providers are rejected.

### Black Box

Black Box captures privacy-sanitized, replayable state transitions. Deterministic digests make experiment and recovery evidence auditable without preserving secrets or raw production identity.

### Mission Control presentation

Mission Control prioritizes current condition and operator decisions before secondary telemetry and diagnostics. Its principal surfaces include:

- System Health;
- Virtual Front Panel;
- Preflight;
- Cooling and thermal readiness;
- Guided Recovery;
- Reliability;
- history and diagnostics.

At widths below 760 pixels, Reliability and other major cockpit regions collapse to a single-column layout. Phone usability is a release constraint, not optional polish.

### Display Manager and AutoPilot

`DisplayManager` converts state and events into 16x2 `DisplayFrame` objects. It owns text fitting, native graphics, priorities, timeouts, transitions, and alert routing.

AutoPilot schedules Flight Deck rotation, honors hardware-button activity, slows rotation when idle, applies night mode, and delegates frame creation to the Display Manager.

### Hardware Manager

`HardwareManager` lazily constructs and caches verified controllers and providers, including:

- A125 LCD;
- buzzer;
- enclosure and topology;
- storage inventory and SMART;
- health services;
- TVS-671 bay LEDs;
- commissioned fan-control paths.

Lazy construction prevents unused hardware paths from being opened during tests or unrelated commands.

### Project Stargate

Stargate is the controlled laboratory for characterizing undocumented hardware. It provides command catalogs, safety classes, simulation and live modes, authorization phrases, captures, repeatability tests, fingerprints, and timing evidence.

Only reproducible, model-verified operations graduate into production adapters.

### Plugins and history

The plugin manager isolates extensions from the core runtime. Plugins may provide collectors, dashboard pages, watchers, notifications, themes, or other registered capabilities.

Historical telemetry and recovery state live outside the source tree. Runtime plugin state, local captures, credentials, and machine-specific evidence remain excluded from Git.

## Host ownership and control

Only one process may own the privileged Host hardware boundary.

The embedded LCD runtime currently owns the production Host boundary. The standalone Host Agent unit remains dormant, lacks a normal enablement path, and requires an explicit marker plus Python activation contract.

Fan-control changes use guarded profiles, restoration logic, dead-man behavior where applicable, and passive verification that commissioned channels returned to motherboard Automatic mode.

Automatic thermal control remains deliberately unarmed unless a separate commissioning decision changes that contract.

## Installation and lifecycle

The native installer deploys to an operator-selected persistent dataset, creates an isolated Python runtime, installs the application service units, and registers `i2c-dev` through the supported TrueNAS Init/Shutdown Scripts API.

Lifecycle operations provide:

- dry-run planning;
- validated staging;
- guarded promotion;
- automatic rollback after failed promotion verification;
- retained backup generations;
- explicit operator rollback;
- repair and cleanup;
- operational verification;
- fail-closed uninstall safety checks.

The application does not rely on generic `/etc/modules-load.d` persistence on TrueNAS.

## Failure containment

TruePanel favors degraded, explainable operation over runtime collapse:

- collector failures return conservative state;
- unknown evidence remains unknown;
- watcher and plugin failures are isolated;
- hardware providers are lazy;
- duplicate writes are suppressed;
- predictive analysis cannot create hard faults;
- reliability correlation retains raw evidence;
- recovery verification is fault-specific;
- simulation rejects production paths;
- destructive storage authority remains outside TruePanel;
- systemd may restart the independent services.

## Testing and promotion gates

The repository uses focused unit and contract tests, full-suite GitHub Actions, installed-wheel smoke testing, HoloDeck scenarios, privacy contracts, responsive-layout checks, and supervised physical-hardware validation where required.

A green simulation suite does not replace a physical hardware gate. A successful hardware test does not grant authority to a different model. Documentation must state which boundary has actually been proven.
