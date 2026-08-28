# Project AEGIS

The next calibration increment and its ecosystem decisions are recorded in the
[AEGIS Prior-Art Field Report](AEGIS_PRIOR_ART_FIELD_REPORT.md). It leaves the
accepted PR #78 baseline frozen and adds a replaceable declarative correlation
policy, adversarial HoloDeck cases, and explicit provenance on a separate
follow-up branch.

Project AEGIS is TruePanel's read-only reliability-intelligence layer. It
connects existing systems without replacing their authority:

1. **ORACLE** identifies statistically unusual drift but cannot invent a hard
   fault.
2. **AEGIS** groups related ORACLE signals and verified alerts into one
   probable root-cause hypothesis with explicit evidence and confidence.
3. **Pathfinder** owns the universal recovery workflow and machine-verification
   state.
4. **Lifeline** supplies the deeper, fail-closed storage recovery path when a
   correlated incident involves physical media.
5. **HoloDeck** rehearses each verifier and measures deterministic scenarios.
6. **Black Box** preserves privacy-sanitized key frames from the rehearsal so
   the evidence can be replayed and audited.

AEGIS has no fan, LCD, bay LED, storage, network, service, or configuration
write path. Correlation does not hide or delete component alerts. It publishes
one operator summary while retaining every contributing alert and its evidence.

## Universal Recovery Coverage Matrix

The matrix is generated from the guidance catalog. A row is `TRUSTED` only when
all of these are present:

- a declared detector;
- diagnostic evidence fields;
- immediate, diagnostic, corrective, and verification guidance;
- a fault-specific automated verifier;
- at least one deterministic regression scenario; and
- a passed fault-present to recovered-state rehearsal.

| Fault | Detector | Machine verifier | Regression coverage |
| --- | --- | --- | --- |
| `cooling.fan_stall` | debounced monitored fan watcher | fan RPM recheck | fan recovery + shared cooling degradation |
| `thermal.high_temperature` | explicit thermal alarm or valid afterburners recommendation | thermal threshold recheck | thermal ramp + shared cooling degradation |
| `storage.smart_warning` | SMART evidence joined to verified ZFS identity | SMART and ZFS recheck | ORACLE drive degradation |
| `storage.disk_faulted` | storage watcher and member evidence | pool/recovery recheck | drive failure and recovery |
| `storage.pool_degraded` | ZFS pool state | pool/recovery recheck | drive/removal recovery |
| `network.link_down` | verified primary link state | link and address recheck | network flap |
| `front_panel.lcd_unavailable` | LCD status bridges | reader and dispatcher recheck | LCD loss/recovery |
| `telemetry.stale` | explicit Host thermal freshness failure | freshness/domain/safety recheck | stale telemetry recovery |

`tests/test_aegis.py::test_recovery_coverage_contract_is_complete_and_ci_enforceable`
is the shipping contract. Adding a guidance code without a coverage definition,
fault-specific verifier, guidance arc, or scenario makes CI fail.

## Shared cooling experiment

`run_shared_cooling_experiment()` reuses ORACLE's bounded fan-bearing scenario.
The fixture warms a baseline, gradually reduces delivered fan RPM, increases
PWM effort up to the physical 255 ceiling, and drifts drive temperature upward.
The comparison thresholds are explicitly lab-only; they are not new production
fault limits.

Current deterministic result:

- AEGIS shared-cause hypothesis: sample **19**;
- first isolated threshold: sample **46**;
- lead: **27 samples**;
- terminal independent alerts: **2**;
- AEGIS incidents: **1**;
- operator alert-count reduction: **50%**;
- cooling verification rehearsal: **PASS**;
- production mutation: **false**.

The report contains two real `BlackBoxFrame.capture()` records: the first AEGIS
hypothesis and the first isolated threshold. Both frames are privacy-sanitized,
and the complete report carries a deterministic SHA-256 digest.

## Confidence semantics

Confidence describes the amount of mutually supporting evidence, not causal
certainty. AEGIS currently scores independent ORACLE signals, matched
correlation rules, and verified hard alerts. It must always say "likely cause"
or "hypothesis" and must retain the supporting values and learned baselines.

## Mission Control Reliability view

The mobile-first view presents:

- the active consolidated incident;
- likely cause and confidence;
- supporting signals;
- the safest next action from existing guidance;
- machine-verification state; and
- Recovery Coverage Matrix gaps.

At widths below 760 px the header, evidence grid, confidence block, and signal
rows collapse to one column. Controls are intentionally absent because AEGIS is
an analysis surface, not a repair actuator.

## Sampling and browser independence

Mission Control may have several dashboard surfaces and several connected
browsers reading the same status API. AEGIS therefore advances ORACLE at most
once per five-second telemetry interval rather than once per HTTP request.

The engine caches the most recent ORACLE outlook behind a thread-safe sampling
gate. Duplicate reads reuse that outlook, while correlation still evaluates
the current verified guidance cards immediately. A newly detected hard alert
therefore appears without waiting for the next predictive sample, but opening
another browser cannot train the learned baseline faster.

The Reliability view consumes the primary dashboard's shared status event and
uses only a one-time fallback request if the initial event was missed. It does
not add another recurring status poll.

SMART recovery verification also fails closed unless both the critical SMART
evidence is clear and the affected member's ZFS state is explicitly `ONLINE`.
The verifier no longer claims an independent ZFS recheck without evaluating
that evidence.

## Failed or rejected approaches

- **Stack directly on the ORACLE draft branch:** rejected because that branch
  predates accepted Pathfinder, Lifeline, and TrueNAS lifecycle merges and its
  diff would delete accepted files. The reusable ORACLE commits were replayed
  onto current `main` instead.
- **Replace component alerts with a correlated incident:** rejected because it
  would hide evidence and make a wrong hypothesis harder to audit. The view
  consolidates presentation only.
- **Treat ORACLE statistics as fault authority:** rejected. Statistical drift
  remains WATCH/DEVELOPING unless an independent detector asserts a hard fault.
- **Use the original unbounded PWM degradation fixture:** rejected after the
  first rehearsal produced values above 255. The scenario now saturates at the
  hardware limit and the measurement was rerun.
- **Call a verifier trusted because guidance text exists:** rejected. Trust now
  requires a deterministic pending-to-passed rehearsal and preserved evidence.

## Remaining risks and next gate

- ORACLE baselines are in-memory and restart with Mission Control.
- Confidence weights are deterministic heuristics and need calibration against
  a larger corpus of sanitized Black Box recordings.
- Current telemetry extraction uses aggregate monitored-fan and hottest-drive
  values; per-zone and per-bay correlations would improve localization.
- The first policy calibration has a small deterministic corpus; its perfect
  synthetic score is not a production false-positive estimate.
- AEGIS has not been deployed or evaluated against live BattleStation data.

The strongest next step is a Black Box calibration campaign: replay normal
workload changes and known incidents through AEGIS, measure false positives and
root-cause stability, then promote only calibrated rules into a production
release candidate. Live deployment remains a separate explicit gate.
