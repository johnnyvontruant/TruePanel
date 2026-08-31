# TruePanel Roadmap

## Current platform

TruePanel 1.2.0 is the stable foundation. The accepted post-1.2 development line adds Pathfinder guided recovery, Lifeline handling for critical SMART evidence, supported TrueNAS `i2c-dev` boot persistence, ORACLE predictive health, AEGIS reliability correlation, Project HANGAR's experiment archive, the first Project FLIGHT DIRECTOR vertical slice, and the GLASS COCKPIT evidence-led Mission Control layout.

AEGIS, HANGAR, Flight Director, and GLASS COCKPIT (PRs #78, #80, #90–#96) are merged to `main` and deployed to BattleStation. Live validation included a genuine active incident (critical SMART evidence on a front-bay drive), which the deployment correctly kept prominent and which directly surfaced and led to fixing a real defect in how lab-rehearsal evidence was scoped.

A further Apple Human Interface Guidelines-inspired visual pass (light/dark mode, translucent glass cards, a restructured Flight Manual card) is deployed on BattleStation's static assets but is **not yet committed back into this repository** — reconciling that is an open 1.3.0 item, tracked below.

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
- Project HANGAR's packaged, CI-validated experiment registry (14 experiments: 10 completed, 2 failed, 2 future);
- Project FLIGHT DIRECTOR's Time Machine, causal map, forecast, what-if rehearsal, and recovery-verification signature;
- GLASS COCKPIT's evidence-led Mission Control command strip and disclosure layout;
- guarded install, upgrade, rollback, repair, verify, cleanup, and uninstall;
- Project Stargate hardware research and Plugin API v1.

## Promotion record and graduation gates

### 1. Preserve the accepted AEGIS baseline — done

- PR #78 passed formal review, 2,348 tests, and installed-wheel smoke;
- request-independent predictive sampling and fail-closed SMART/ZFS verification have dedicated regressions;
- the reviewed commit history remains preserved;
- later research, calibration, and deployment evidence belong on separate branches.

### 2. Calibrate predictive behavior — in progress

- persist ORACLE baselines safely across Mission Control restarts;
- replay normal workload changes and known incidents from sanitized Black Box recordings;
- measure false-positive rate, detection lead, and root-cause stability;
- tune confidence weights from evidence rather than intuition;
- retain clear `NORMAL`, `WATCH`, `DEVELOPING`, and `FAULT` authority boundaries.

AEGIS's field-evidence gate (PR #91) formalized this: the current synthetic
corpus verdict is explicitly "lab calibrated," not field-eligible or
production-validated, until a separately governed, opt-in corpus of real
recordings is collected.

### 3. Improve localization — open, targeted for 1.3.0

- move from aggregate fan and hottest-drive evidence toward fan-zone and drive-bay relationships;
- correlate PWM effort, delivered RPM, thermal sensors, drive temperatures, and physical topology;
- report which zone, fan, bay, or interface most likely explains the incident;
- preserve uncertainty when topology evidence is incomplete.

### 4. Complete live read-only evaluation — done

- deployed to BattleStation through the guarded upgrade lifecycle with a
  retained rollback generation and zero post-promotion service errors;
- a genuine live incident (critical SMART evidence, bay 3, pool `HDDs`,
  `raidz1-0`) validated that Mission Control keeps real faults prominent
  even when SMART self-assessment and ZFS state both still report healthy;
- that same live incident surfaced a real defect — HoloDeck reference-
  rehearsal evidence could be read as applying to the active incident — which
  was fixed and reverified live (PR #96, main at `43dca73`);
- Mission Control was confirmed on desktop and phone against a real
  incident, not only fixtures;
- the production fingerprint and rollback generation remain retained.

### 5. Finish the documentation and visual record — in progress

- keep README, Mission Control, architecture, installation, lifecycle, recovery, and release documentation synchronized;
- replace stale screenshots after the final cockpit layout is accepted;
- document stable versus experimental features plainly;
- publish the Prior-Art Field Report and adopted-code provenance before incorporating external work;
- **new:** commit the deployed Apple HIG-inspired Mission Control visual
  system (light/dark mode, glass cards, restructured Flight Manual card)
  back into this repository — it currently exists only on BattleStation's
  static assets, deployed by hand rather than through the guarded upgrade
  lifecycle, which is a real gap between the repository and the running
  system that should close before 1.3.0.

## Toward 1.3.0

With gates 1 and 4 closed and gate 5 nearly closed by this changelog and
roadmap update, the remaining work for a `v1.3.0` tag is:

1. Commit the Mission Control visual redesign into this repository (gate 5),
   reconciling it with `claude/mission-control-apple-redesign-oitcxc`, an
   independent unmerged branch covering similar ground.
2. Close gate 3 (localization) — move fan and drive-temperature evidence
   from aggregate to per-bay/per-zone.
3. Scope the diagnostic half of Project CHECKRIDE: bind a real storage
   incident to a personalized, staged replacement checklist and HoloDeck
   rehearsals (correct bay, wrong bay, undersized replacement, stalled
   resilver, and so on). Actual replacement execution stays manual and
   guarded — CHECKRIDE's automation stops at guidance and rehearsal, not
   storage mutation, by explicit decision.
4. Repository hygiene: prune branches already merged into `main`, and
   decide the disposition of long-diverged experiment branches.
5. Tag `v1.3.0-rc1` once 1–4 land, following the existing RC pattern.

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
- keep destructive or security-sensitive actions manual and guarded;
- Project CHECKRIDE will bind a real storage incident to a personalized
  replacement runbook and HoloDeck rehearsals; by explicit product decision,
  it stops at guidance and verification and does not gain authority to
  execute `zpool`/`zfs` replacement or any other destructive storage
  operation. An "advanced" operator mode has been deliberately deferred
  rather than built, specifically to avoid a new user reaching for
  read-write automation before they understand the guardrails it removes.

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
