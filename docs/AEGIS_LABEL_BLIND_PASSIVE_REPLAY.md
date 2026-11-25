# AEGIS Label-Blind Passive Replay

## Outcome

This increment independently reconstructs one confirmed recording intake, replays the exact 48 sanitized samples without labels, and preserves a content-addressed diagnosis receipt. The fixed detector requires corroborating fan RPM, fan-speed ratio, CPU, system, and physical-disk temperature drift. It reports a probable shared chassis-cooling cause with explicit evidence and confidence, and compares the first correlated match with separately declared isolated drift thresholds.

Success reaches only `REPLAY_EVIDENCE_PRESERVED_FOR_MANUAL_REVIEW`. It does not field-validate, accept, install, promote, deploy, capture, modify runtime state, or actuate hardware.

## HoloDeck proof

- Thirteen deterministic paths: one replay ready and twelve HOLD.
- HOLD covers intake-receipt substitution, recording drift, labels, noncanonical bytes, unstable baseline, nonmonotonic time, confirmation substitution, unsafe permissions, symlinks, authority escalation, insufficient evidence, and duplicate replay.
- Five independent supporting signals produce 0.95 hypothesis confidence.
- Shared-cooling evidence first matches at sample 19; isolated drift thresholds first match at sample 46: 27 samples earlier.
- Recovery Coverage Matrix remains 8/8 trusted with zero gaps.
- Labels revealed, live captures, BattleStation accesses, validations, acceptances, installations, deployments, hardware actions, and runtime writes: zero.
- Preserved evidence: `docs/evidence/aegis-temperature-label-blind-passive-replay-v1.json` (`1589618f0c5747490782b556e2b9c09d485cceac019772ab68092275c4f7709b`).

## Prior-Art Field Report

| Candidate | Actual code or documentation inspected | Capability, maturity, fit, security, licence | Recommendation |
|---|---|---|---|
| [OpenTelemetry Collector filelog receiver](https://github.com/open-telemetry/opentelemetry-collector-contrib/blob/504480882aa709e0a665bfff10a1263505c89fc1/receiver/filelogreceiver/README.md) | The beta receiver fingerprints files, tracks offsets and record numbers, resumes through checkpoints, and can delete after reading behind a feature gate. Current commits and tests show very active maintenance. | Apache-2.0, mature collector ecosystem. Its globbing, tailing, checkpoint writes, optional deletion, and live collector process conflict with the one-shot no-capture boundary. | Adapt explicit progress identity and duplicate prevention; do not import or run the receiver. |
| [River ADWIN](https://github.com/online-ml/river/blob/9279feaafac8814b7dc7d24cea0c7950a56154b3/river/drift/adwin.py) | Uses adaptive subwindows and a significance parameter to detect distribution change with mathematical guarantees; the implementation delegates its hot path to a Rust extension. The repository was active on 2026-11-01 UTC. | BSD-3-Clause, broad online-ML tests and active maintenance. Online adaptation would move the decision boundary during the evidence replay and add native dependency weight. | Revisit for future field drift surveillance; reject for this fixed, reviewable replay contract. |
| [ruptures PELT](https://github.com/deepcharles/ruptures/blob/ee1c8ff8a548d54c641b2bb471562165931f31c7/src/ruptures/detection/pelt.py) | Computes penalized offline segmentation using pluggable cost functions and pruning; recent releases support current Python versions. | BSD-2-Clause, research maturity and good documentation, but requires NumPy/SciPy and penalty/model choices that would need separate calibration. | Promising independent challenger for longer traces; do not add it to the narrow 48-sample gate. |
| [OpenTelemetry file storage](https://github.com/open-telemetry/opentelemetry-collector-contrib/blob/504480882aa709e0a665bfff10a1263505c89fc1/extension/storage/filestorage/README.md) | Persists receiver state and offsets in a dedicated writable directory. | Apache-2.0 and maintained, but introduces a mutable operational store and extra write authority. | Retain TruePanel's exclusive digest-keyed receipt instead. |
| `rewind` deterministic incident replay | Public documentation describes always-on eBPF capture, a production ring buffer, network/database traffic capture, webhook flushes, and local re-execution. | Interesting causal-replay architecture, but far broader privilege, privacy, network, and supply-chain surface than a NAS telemetry receipt. Maturity and operational safety are not yet sufficient for this gate. | Architectural inspiration only; reject integration and all production capture behavior. |

## Build versus adopt

The strongest shortcut is conceptual rather than a dependency: OpenTelemetry's fingerprint/offset identity reinforces exact replay position, River shows how to distinguish fixed evidence from adaptive learning, and ruptures supplies a credible future independent challenger. TruePanel keeps a small standard-library implementation because the input is already bounded, canonical, and content-addressed; the detector contract must remain visible and immutable before labels exist.

No third-party code, package, schema, binary, service, credential, key, or dataset was incorporated. No new attribution file is required. The best collaboration opportunity is the River maintainers: ask how to publish a frozen, non-learning ADWIN challenger whose parameters and entire decision trace can be independently attested.

## Failed and rejected paths

- Calling the existing producer detector was rejected; this replay independently computes baselines, evidence deltas, confidence, match index, and lead.
- Adaptive online learning was rejected because it would alter thresholds during the evidentiary replay.
- Trusting the intake receipt alone was rejected; confirmation, recording bytes, privacy, custody, sequence, and stable baseline are reconstructed again.
- Accepting labels or outcome hints was rejected before replay.
- A semantically equivalent but byte-different recording was rejected.
- Replaying a second time into the same receipt slot was rejected.
- Live file tailing, glob discovery, checkpoint stores, deletion, eBPF capture, network replay, and service processes were rejected.
- A stable trace is not forced into a diagnosis; insufficient shared-cooling evidence remains HOLD.

## Open risks and next step

The detector thresholds are predeclared and deterministic but still calibrated only against a synthetic 48-sample trace. The five signals share one fixture clock and do not prove independent sensor quality. The 0.95 value is an explicit evidence-weight score, not a field-calibrated probability. A pseudonymous recording may still be re-identifiable when combined with external context.

The next safe increment is a separately authenticated manual replay-review receipt. It should let JT record `ACCEPT_EVIDENCE` or `HOLD_EVIDENCE` over this exact replay, with rationale and expiry, while remaining unable to call the result field validation, install or promote a candidate, deploy, capture, or actuate hardware.
