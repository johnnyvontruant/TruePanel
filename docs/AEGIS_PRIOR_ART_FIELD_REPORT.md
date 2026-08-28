# AEGIS Prior-Art Field Report

Research date: 2026-08-28

This report records the public-software survey behind the first AEGIS
calibration follow-up. It is a dependency and provenance decision record, not
an endorsement list. PR #78 and `feature/project-aegis` remain the frozen
baseline; this work starts from accepted `main` and depends on that baseline.

## Decision

Adopt Prometheus Alertmanager's **grouping and inhibition semantics** as an
architectural pattern behind a TruePanel-owned `CorrelationPolicy` interface.
Do not import Alertmanager or copy its Go implementation. In TruePanel,
"inhibition" changes only the consolidated presentation count: raw alerts and
their evidence are retained, and the policy has no notification, repair, or
control authority.

The first declarative rule replaces the old "any two cooling anomalies"
heuristic. A shared-cooling hypothesis now requires evidence from two distinct
groups:

1. reduced fan delivery, from predictive RPM evidence or a verified fan-stall
   alert; and
2. corroborating fan effort, downstream temperature, an ORACLE cooling rule,
   or a verified thermal alert.

Every evidence item has an explicit confidence weight and source namespace.
The policy declares its presentation keys, inhibited symptom alerts, confidence
cap, and deterministic HoloDeck verification scenario. CI rejects incomplete
rules.

## Candidate comparison

| Candidate | Capability and maturity | Fit, weight, and security | License and use | Recommendation |
| --- | --- | --- | --- | --- |
| [Prometheus Alertmanager](https://github.com/prometheus/alertmanager) | Established alert deduplication, grouping, silencing, and inhibition; code, configuration validation, fuzz tests, and HA design were inspected at `f6c84d3` (2026-08-27). | Excellent semantic fit; running its Go service would duplicate TruePanel's local alert path and add routing/secret surfaces. | Apache-2.0. Architectural adaptation only; no copied code and therefore no bundled notice required. Provenance remains in code and this report. | **Adapt now** behind TruePanel's interface. Revisit a webhook bridge only if external notification routing becomes a real requirement. |
| [Home Assistant Repairs](https://github.com/home-assistant/core/tree/dev/homeassistant/components/repairs) | Mature issue registry plus separate guided fix flows. Registry, flow manager, websocket surface, and tests were inspected at `1057ceb` (2026-08-28). | Strong confirmation of AEGIS's issue-versus-fix authority split. Importing Home Assistant Core is infeasible and unnecessary. | Apache-2.0. Architectural inspiration only. | **Adapt the contract**, not the code: detection can create a fixable issue, but resolution requires a separate verified flow. Pathfinder already provides the right boundary. |
| [River](https://github.com/online-ml/river) | Actively maintained online ML with ADWIN and Page-Hinkley drift detectors and regression tests; inspected at `64285b9` (2026-08-21). | Algorithmically strong, but the package's broader numerical stack and model surface are disproportionate for the current TrueNAS appliance path. Detector outputs would still need TruePanel-specific authority and calibration. | BSD-3-Clause. No code incorporated. | **Benchmark later** through an optional detector adapter against a large sanitized Black Box corpus; do not add the runtime dependency yet. |
| [Scrutiny](https://github.com/AnalogJ/scrutiny) | Mature SMART collection and dashboard using manufacturer status plus real-world failure-rate thresholds; collector, threshold models, troubleshooting guidance, and tests inspected at `89588a4` (2026-08-20). | Excellent disk-health reference. Its Go collector, database, web application, device access, and scheduled execution duplicate existing TruePanel/TrueNAS responsibilities. Some deployment modes require raw device access. | MIT. No code incorporated. | **Collaborate/compare**, especially on drive-model thresholds and evidence semantics. Keep TrueNAS as the storage authority and retain fail-closed SMART/ZFS identity checks. |
| [smartmontools](https://github.com/smartmontools/smartmontools) | Authoritative `smartctl`/`smartd` implementation for ATA, SCSI/SAS, and NVMe health. | Already the right upstream evidence source through bounded subprocess parsing. Library/code embedding would create GPL and portability work without improving authority. | GPL-2.0-or-later upstream. Existing command invocation is retained; no source copied or linked. | **Use as an external evidence provider**, track exit-bit and JSON schema behavior, and never infer ZFS membership from SMART alone. |
| [TrueNAS middleware](https://github.com/truenas/middleware) | Canonical platform API, alert, disk, pool, and service behavior with a large test tree. | Best source for platform semantics. Direct internal imports would couple TruePanel to private release internals; read-only supported APIs are safer. | LGPL-3.0. No code incorporated. | **Follow and integrate through supported read-only APIs**. Treat it as storage/platform authority, not a code library. |
| [Chaos Mesh](https://github.com/chaos-mesh/chaos-mesh) | CNCF project with declarative fault objects, workflows, status checks, admission validation, and broad fault coverage. | Excellent fault-contract ideas, but Kubernetes, privileged daemons, and live injection are unacceptable weight and authority for this NAS path. | Apache-2.0. Architectural inspiration only. | **Adapt declarative scenario/status concepts** inside hardware-isolated HoloDeck. Do not run Chaos Mesh or privileged injection on the host. |
| [Goss](https://github.com/goss-org/goss) | Mature declarative server validation with wait/retry and health-endpoint modes. | Useful model for post-recovery assertions. Shipping another binary and allowing arbitrary host commands would widen the security boundary. | Apache-2.0. No code incorporated. | **Adapt the assertion style** to existing fault-specific Python verifiers; consider offline export only after a constrained schema exists. |
| [StackStorm](https://github.com/StackStorm/st2) | Established event/rule/workflow/action automation with audit trails and many integration packs. | Valuable future model for sensors versus gated actions. Its multi-service stack, credentials, runners, and broad execution authority are far beyond AEGIS's read-only scope. | Apache-2.0. No code incorporated. | **Architecture reference only**. Pathfinder should keep narrower workflows and explicit human gates. |
| [Netdata](https://github.com/netdata/netdata) | Broad real-time infrastructure monitoring, alerts, metric correlations, and anomaly features. | High capability but large overlapping agent/UI surface and a materially heavier dependency/security footprint. Licensing and distribution model require careful separate review. | GPLv3+ repository with additional distribution/product considerations. No code incorporated. | **Reject for embedding**. Use its metric-correlation UX as competitive reference. |
| [OpenTelemetry semantic conventions](https://github.com/open-telemetry/semantic-conventions) | Widely adopted naming conventions that make telemetry interoperable and correlatable. | Low conceptual weight, but adopting the SDK/collector now would not improve AEGIS's local evidence quality. | Apache-2.0. No code incorporated. | **Map later** at an export boundary; keep internal names stable until that boundary exists. |

## Prototype incorporated

`truepanel.aegis.policy` is the clean adaptation:

- `CorrelationPolicy` is the replaceable TruePanel-owned protocol;
- `DeclarativeCorrelationPolicy` evaluates source-namespaced evidence groups;
- `HypothesisRule` carries grouping, inhibition, confidence, and verification
  metadata;
- Mission Control receives the active policy ID and semantics;
- raw verified alerts are always retained;
- `validate_correlation_policy()` is the CI contract;
- no new runtime dependency, subprocess, network listener, credential, or host
  permission was added.

The HoloDeck calibration corpus includes one positive and three adversarial
negative cases. Results are deterministic, evidence-digested, and explicitly
limited to a small synthetic corpus:

The preserved machine-readable result is
[`docs/evidence/aegis-correlation-calibration-v1.json`](evidence/aegis-correlation-calibration-v1.json).

| Measure | Result |
| --- | ---: |
| Positive shared-cooling detection | sample 19 |
| First isolated threshold | sample 46 |
| Detection lead | 27 samples |
| Confusion matrix | 1 TP / 0 FP / 3 TN / 0 FN |
| Precision / recall / specificity | 1.000 / 1.000 / 1.000 |
| Negative scenarios misclassified by old heuristic | 2 of 3 |

These figures prove deterministic behavior for this corpus, not production
accuracy. A larger, privacy-sanitized Black Box corpus remains required before
deployment.

## Rejected and failed paths

- **Import River now:** rejected because a mature detector cannot substitute
  for labeled TruePanel evidence, and its dependency cost precedes the needed
  corpus.
- **Run Scrutiny alongside TruePanel:** rejected because duplicate collection,
  raw-device permissions, scheduling, database, and web UI add more failure
  modes than verified development time saved.
- **Treat all temperature drift as cooling failure:** failed in simulation.
  Ambient and workload scenarios produced two or more unusual cooling metrics
  without loss of fan delivery.
- **Hide inhibited alerts:** rejected. Alertmanager-style inhibition is useful
  for presentation, but AEGIS preserves all raw alerts and evidence for audit.
- **Adopt a general auto-remediation engine:** rejected at this authority stage.
  StackStorm demonstrates the value of rules/actions/audit separation, while
  also demonstrating why broad action runners do not belong inside read-only
  AEGIS.
- **Use privileged chaos tooling on the NAS:** rejected. HoloDeck keeps fault
  injection deterministic, in-memory, and hardware-isolated.

## Security and licensing conclusion

No third-party source, binary, package, model, dataset, or credentials were
added. The incorporated work is an attributed architectural adaptation of
Apache-2.0 semantics expressed in original TruePanel code. Existing MIT
project licensing is unchanged. The policy has no I/O or execution capability,
and all tests use deterministic in-memory telemetry.

## Most promising collaboration

The highest-value outreach target is **AnalogJ/Scrutiny**: compare its
drive-model and Backblaze-derived threshold semantics with TruePanel's
privacy-sanitized SMART/ZFS evidence model. A focused exchange could save
calibration time without adopting Scrutiny's collector or weakening TrueNAS
authority. A second valuable technical discussion is with River maintainers
about a minimal, dependency-conscious drift-detector boundary suitable for an
appliance; no contact was made during this work.

## Strongest next step

Build a versioned, privacy-sanitized Black Box calibration corpus containing
normal workload shifts, seasonal ambient changes, sensor dropouts, real fan
degradation, and storage incidents. Run the built-in policy and an optional
River-backed detector through the same interface, then publish per-scenario
false-positive rate, lead time, confidence stability, and root-cause stability.
