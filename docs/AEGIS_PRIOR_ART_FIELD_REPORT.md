# AEGIS Prior-Art Field Report

Research dates: 2026-08-28 through 2026-09-02

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

## Corpus/versioning follow-up

The second survey focused on the missing evidence-data contract rather than a
new detector:

| Candidate | What was inspected | Decision and license |
| --- | --- | --- |
| [DVC](https://dvc.org/doc/user-guide/project-structure/dvc-files) | Small tracked descriptors carry paths, hashes, sizes, and file counts while content remains addressable. | **Adapt the content-addressed manifest idea.** Full DVC and remote/cache machinery are disproportionate for 193 small committed frames. Apache-2.0; no code incorporated. |
| [River progressive validation](https://riverml.xyz/dev/api/evaluate/progressive-val-score/) | Ordered streaming evaluation measures the prediction before later truth/update, with optional label delay. | **Adapt ordered frame-by-frame scoring now; benchmark River later.** The corpus records first detection, frame false positives, confidence variance, and post-detection stability without adding River. BSD-3-Clause; no code incorporated. |
| [Frictionless Data Package](https://specs.frictionlessdata.io/data-package/) | A central descriptor enumerates resources plus dataset-level metadata, paths, and schemas. | **Adapt the compact package shape.** TruePanel's domain-specific manifest is smaller and adds privacy/challenge assertions. Specification ideas only; no library or source incorporated. |
| [Great Expectations](https://docs.greatexpectations.io/docs/core/run_validations/create_a_validation_definition/) | Validation definitions bind a batch to an expectation suite and preserve structured results. | **Adapt expectations/results separation.** The runtime and dependency graph are too heavy for six appliance fixtures. Apache-2.0; no code incorporated. |
| [MLCommons Croissant](https://docs.mlcommons.org/croissant/docs/croissant-spec-1.0.html) | Rich dataset/resource metadata emphasizes portability, reproducibility, provenance, and responsible-use context. | **Defer adoption.** It is valuable when the corpus becomes publishable/interoperable ML data; it is excessive for private JSONL regression fixtures. Metadata concepts only; no package or schema copied. |

The resulting `aegis-black-box-corpus-v1` uses original TruePanel code and
MIT-licensed synthetic fixture data. Its manifest identifies provenance,
privacy state, license, generator, limitations, resource hashes, labels, and
challenge classes. CI verifies both the corpus and its preserved validation
report. No third-party notice-bearing artifact was added.

## Field-evidence and statistical-promotion follow-up

Research on 2026-08-30 challenged the remaining assumption that an observed
perfect score can authorize trust:

| Candidate | Useful result | Decision and provenance |
| --- | --- | --- |
| [NIST confidence-interval guidance](https://www.itl.nist.gov/div898/handbook/prc/section2/prc241.htm) | NIST describes Wilson score intervals as a robust proportion interval across values of `p` and `n`, unlike a naive point estimate. | **Adapt the published formula** in original, dependency-free TruePanel code. Mathematical method only; no source copied. |
| [Datasheets for Datasets](https://arxiv.org/abs/1803.09010) | Documents motivation, composition, collection, uses, distribution, and maintenance so consumers can evaluate data beyond its bytes. | **Adapt factual provenance questions** to a small field-corpus manifest. Paper is architectural inspiration; no template or text copied. |
| [Google Data Cards Playbook](https://sites.research.google/datacardsplaybook/) | Emphasizes purposeful, people-centered dataset transparency and context that cannot be inferred automatically. | **Adapt the admission-versus-validation split.** CC BY-SA playbook content is not copied; original field names are used. |
| [Evidently](https://github.com/evidentlyai/evidently) | Mature Apache-2.0 offline/production evaluation with extensible metrics, tests, monitoring, and drift detection. | **Defer the dependency.** Its broad stack is excessive before real field data exists; benchmark later behind `IncidentDetector`. No code incorporated. |

The resulting evidence gate adds no package, model, service, listener, data, or
credential. Wilson calculations use the Python standard library. Field-data
admission requires operator opt-in, sanitized-at-rest evidence, reviewed labels,
declared allowed use, and retention policy. Automated success can produce only
a field candidate; it cannot issue a production-validation receipt.

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

## Recovery-ground-truth follow-up

The 2026-09-02 survey inspected in-toto Statement v1, W3C PROV-DM,
Sigstore/Cosign attestation verification, restic repository-check semantics,
OpenZFS replacement rules, and GUAC's provenance graph. The selected shortcut
is an original, dependency-free TruePanel statement and ledger shaped by
in-toto's subject/digest/predicate separation and W3C's
entity/activity/agent distinction. No source was copied and no runtime
dependency was added.

The key invalidated assumption is that a SHA-256-bearing receipt proves who
made a claim. It does not. AEGIS now labels digests as integrity-only and
separately enforces provider mode, source reference, incident identity,
freshness, semantic claims, and contradiction handling. See
[`AEGIS_RECOVERY_GROUND_TRUTH.md`](AEGIS_RECOVERY_GROUND_TRUTH.md) for the
comparison, licensing decisions, rejected routes, HoloDeck measurements, and
next adapter boundary.

## Passive TrueNAS provider follow-up

The 2026-09-02 adapter study inspected the documented TrueNAS 25.10
`disk.query`, `replication.query`, and `cloud_backup.query` contracts plus the
corresponding middleware implementations and LGPLv3 license. The supported
read-only APIs are the best platform-fit shortcut: they expose disk identity,
capacity, pool membership, and protection-task state without importing private
middleware internals or adding a cloud service, credential, or runtime
dependency.

Two attractive shortcuts were rejected. A successful replication or cloud
backup task proves transfer completion, not a tested restore. A disk absent
from a pool is not necessarily blank or disposable. TruePanel therefore
requires a separate incident-bound restore receipt and agreement between
TrueNAS inventory and local read-only signature evidence. Run and restore
methods remain outside the allowlist because the middleware assigns them write
authority.

The implementation is original TruePanel code behind replaceable provider
interfaces; no TrueNAS source was copied. See
[`AEGIS_PASSIVE_TRUENAS_PROVIDERS.md`](AEGIS_PASSIVE_TRUENAS_PROVIDERS.md) for
the exact trust boundary, three adversarial HoloDeck paths, licensing notes,
and deferred live-runtime gate.
