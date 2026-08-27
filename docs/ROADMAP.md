# TruePanel Roadmap

## Current platform

TruePanel 1.2.0 is the stable foundation. The accepted post-1.2 development line adds Pathfinder guided recovery, Lifeline handling for critical SMART evidence, supported TrueNAS `i2c-dev` boot persistence, ORACLE predictive health, and the first read-only AEGIS reliability increment.

AEGIS passed formal review in PR #78 and remains undeployed on the reference NAS.

The platform now includes:

- a physical 16x2 LCD Flight Deck and button dispatcher;
- a responsive Mission Control cockpit and Virtual Front Panel;
- structured health monitoring and historical telemetry;
- physical-to-logical storage and bay awareness;
- guarded fan profiles and thermal readiness;
- passive compatibility, Host readiness, fan-safety, and acceptance checks;
- Preflight readiness and privacy-safe support bundles;
- Pathfinder recovery sessions and machine verification;
- Lifeline critical-SMART recovery;
- HoloDeck Digital Twin and deterministic fault injection;
- Black Box recording, replay, and incident compilation;
- ORACLE adaptive baselines and developing-fault analysis;
- AEGIS incident correlation and a CI-enforced Recovery Coverage Matrix;
- guarded install, upgrade, rollback, repair, verify, cleanup, and uninstall;
- Project Stargate hardware research and Plugin API v1.

## Promotion record and graduation gates

### 1. Preserve the accepted AEGIS baseline

- PR #78 passed formal review, 2,348 tests, and installed-wheel smoke;
- request-independent predictive sampling and fail-closed SMART/ZFS verification have dedicated regressions;
- the reviewed commit history remains preserved;
- later research, calibration, and deployment evidence belong on separate branches.

### 2. Calibrate predictive behavior

- persist ORACLE baselines safely across Mission Control restarts;
- replay normal workload changes and known incidents from sanitized Black Box recordings;
- measure false-positive rate, detection lead, and root-cause stability;
- tune confidence weights from evidence rather than intuition;
- retain clear `NORMAL`, `WATCH`, `DEVELOPING`, and `FAULT` authority boundaries.

### 3. Improve localization

- move from aggregate fan and hottest-drive evidence toward fan-zone and drive-bay relationships;
- correlate PWM effort, delivered RPM, thermal sensors, drive temperatures, and physical topology;
- report which zone, fan, bay, or interface most likely explains the incident;
- preserve uncertainty when topology evidence is incomplete.

### 4. Complete live read-only evaluation

- deploy only after an explicit approval and rollback plan;
- observe BattleStation telemetry without actuation;
- verify normal workloads do not generate misleading incidents;
- confirm Mission Control remains excellent on desktop and phone;
- compare AEGIS evidence with the physical LCD, service state, and existing watchers;
- retain the production fingerprint and rollback generation.

### 5. Finish the documentation and visual record

- keep README, Mission Control, architecture, installation, lifecycle, recovery, and release documentation synchronized;
- replace stale screenshots after the final cockpit layout is accepted;
- document stable versus experimental features plainly;
- publish the Prior-Art Field Report and adopted-code provenance before incorporating external work.

## Wide-net ecosystem expedition

TruePanel should not rebuild solved problems merely because they were solved elsewhere.

The project will search GitHub and the wider software ecosystem for transferable work in:

- TrueNAS, QNAP, NAS, and homelab monitoring;
- SMART analysis and predictive disk health;
- anomaly detection and multi-signal root-cause analysis;
- digital twins, record/replay, and deterministic fault injection;
- incident management, runbooks, and machine-verifiable recovery;
- hardware telemetry, BMC/IPMI, dashboards, and notification systems.

Candidates will be evaluated for capability, maintenance health, tests, dependency weight, security posture, license compatibility, attribution, and verified time saved.

Strong external work may be adopted or adapted behind a TruePanel-owned interface with provenance, required notices, and replacement tests. Ambiguously licensed, insecure, abandoned-risk, or unnecessarily heavy dependencies will be rejected.

## Compatibility expansion

- formalize community hardware profiles;
- make passive compatibility evidence easier to submit and compare;
- validate additional QNAP models through Stargate and HoloDeck fixtures;
- separate portable capabilities from model-specific controls;
- build a privacy-safe compatibility replay corpus;
- document explicit commissioning gates for LCD, fan, buzzer, and bay-LED hardware.

## Recovery expansion

- extend the Recovery Coverage Matrix as new guidance codes are added;
- deepen drive replacement, pool recovery, thermal, network, LCD, service, and telemetry runbooks;
- add clearer human-physical-verification checkpoints;
- preserve resolution evidence and recovery timelines;
- explore safe notification and escalation integrations;
- keep destructive or security-sensitive actions manual and guarded.

## Mission Control evolution

- retain the cockpit priority of need-to-know before nice-to-know;
- keep phone usability as a release contract;
- improve incident localization and evidence comparison;
- add calm history views for predictions, incidents, actions, and verified recoveries;
- make degraded or unavailable data obvious without creating alert fatigue;
- preserve the Virtual Front Panel appearance and ordered hardware ownership.

## HoloDeck and Black Box evolution

- expand deterministic recovery scenarios;
- converge older chaos vocabulary with current channel-, bay-, interface-, and sensor-specific events;
- grow the privacy-safe calibration corpus;
- add compatibility replay across hardware profiles;
- turn verified field failures into minimal regression fixtures;
- keep all generated artifacts bounded, sanitized, data-only, and hardware-isolated.

## Longer horizon

Possible later work includes:

- notification and event-export integrations;
- additional LCD or OLED backends;
- richer plugin isolation and signed packages;
- declarative Mission Control layouts;
- community-maintained hardware profiles;
- optional authenticated remote access patterns;
- carefully bounded self-healing for actions that are proven reversible and independently verified.

Self-healing is not a shortcut around recovery evidence. No automatic action should graduate until detection, rollback, verification, failure containment, and model-specific authority have all been demonstrated.

## Guiding rule

TruePanel should make old hardware more understandable, repairable, and useful without making the appliance less trustworthy.

Explore aggressively. Test assumptions. Reuse good ideas wherever they come from. Preserve hard safety floors around production stability, destructive storage operations, security, and hardware authority. Every detected fault should lead toward an actionable, verifiable recovery path.
