# AEGIS drive-temperature telemetry blind spot

## Decision

The AEGIS v2 coverage candidate treats the absence of a temperature record for
an explicitly present, identified storage member as an actionable observability
fault. The candidate is rehearsed but unaccepted and uninstalled. It does not
assign a temperature, assert overheating, or authorize a repair. When SMART or
ZFS fault evidence names the same exact device or physical bay, Mission Control
presents one probable shared drive-health and telemetry-path incident while
retaining both raw alerts.

The proposed safe next action is read-only: reconcile member identity, inspect existing
SMART/ZFS evidence, and recover the narrowest collector or mapping path. The
machine verifier requires every expected member to report an identity-matched
temperature for three consecutive observations.

## Deterministic result

The HoloDeck fixture models three present RAIDZ members. Bay 3 loses its
temperature record while its SMART evidence reports two pending sectors.

| Measure | Result |
| --- | ---: |
| AEGIS detection | sample 1 |
| Isolated temperature threshold | never fires |
| Raw actionable cards | 2 |
| Consolidated incidents | 1 |
| Presentation reduction | 50% |
| Hypothesis confidence | 0.84 |
| False overheating claims | 0 |
| Cross-drive false correlations | 0 |
| Required complete recovery observations | 3 |
| Writes / hardware actions | 0 / 0 |

The preserved report contains five cases: complete inventory, exact-member
SMART correlation, mismatched-drive SMART separation, no-authoritative-inventory
silence, and sustained restoration. Two sanitized Black Box frames preserve the
baseline and fault state.

## Prior-Art Field Report

Inspected on 2026-10-08. Repository activity and popularity are snapshots, not
security guarantees.

| Candidate | Actual code/documentation inspected | Capability and lesson | Maturity, tests, platform fit, weight | Security and license | Build versus adopt / time saved |
| --- | --- | --- | --- | --- | --- |
| [Prometheus `absent()` / `absent_over_time()`](https://prometheus.io/docs/prometheus/latest/querying/functions/#absent) and [Prometheus repository](https://github.com/prometheus/prometheus) | Official query-function semantics and current repository metadata | Missing expected series are first-class alert inputs rather than zero-valued measurements. The time-window form supports sustained recovery semantics. | Very mature and actively maintained; extensive Go tests. A full TSDB/exporter stack is disproportionate for an embedded local dashboard. | Apache-2.0. Strong isolation model, but deployment would add listeners, retention, and configuration surface. | **Adapt the absence semantics.** Saves design/calibration time; do not add the runtime. |
| [Zabbix history functions](https://www.zabbix.com/documentation/current/en/manual/appendix/functions/history) and [`nodata()` implementation tree](https://github.com/zabbix/zabbix) | Official trigger documentation and current server source tree | `nodata()` demonstrates that missing collection can have its own trigger/recovery window and must be distinguished from a numeric threshold. | Mature, broad test surface, actively maintained. Poor dependency fit: server/database/agent architecture is much heavier than TruePanel's in-process snapshot. | GPL-2.0-or-later; linking or copying would create obligations incompatible with this narrow MIT-owned module. | **Idea only.** Reject runtime/code reuse; retain the explicit no-data state and window. |
| [smartmontools JSON implementation](https://github.com/smartmontools/smartmontools/blob/master/smartmontools/json.cpp) and [project repository](https://github.com/smartmontools/smartmontools) | Actual JSON key normalization/serialization code plus project metadata | Stable structured output is the right adapter boundary for temperature and SMART evidence; missing keys remain distinguishable from numeric values. | Long-lived, actively maintained C/C++ project with regression coverage and excellent NAS/Linux fit. Already adjacent to TrueNAS tooling, but invoking it here would duplicate existing collectors. | GPL-2.0-or-later. No source copied. Subprocess inputs and device access would require a separate least-privilege review. | **Reuse upstream output through existing collectors, not a new invocation.** Saves a custom SMART parser. |
| [Prometheus Alertmanager](https://github.com/prometheus/alertmanager) | README, repository metadata, and existing grouping/inhibition model already adapted by AEGIS | Group related notifications while retaining source alerts. For this fault, grouping is safe only after an exact member-identity join. | Mature, active, heavily tested. External service would add operational weight and cannot perform TruePanel's storage-identity proof by itself. | Apache-2.0. Network/API hardening would be required if deployed. | **Retain the existing TruePanel-owned correlation interface.** Adapt grouping, not the service. |
| [TrueNAS Drive Health Management](https://www.truenas.com/docs/scale/25.10/scaletutorials/scaletutorialsprint/#drive-health-management) | Official drive-health/SMART guidance already used by Pathfinder | SMART state and ZFS membership are independent evidence; a missing temperature must not be promoted into either one. | First-party platform fit and low conceptual weight. APIs and payload details remain version-sensitive. | Documentation used as guidance; no code copied. Existing read-only boundaries remain in force. | **Use existing snapshot evidence.** Avoid a second poller or privileged device query. |

### Adopted or adapted work

No third-party code, package, service, schema, credential, or dataset was added.
TruePanel adapts three ideas behind its own replaceable interfaces:

- Prometheus/Zabbix: missing telemetry is a distinct state, not zero;
- Alertmanager: consolidate presentation but retain raw alerts;
- smartmontools: preserve structured absence and consume existing collector
  output rather than parsing human text.

There are no new notice-file obligations or runtime dependencies.

### Rejected paths

- Treating an absent temperature as `0`, normal, or cool: converts uncertainty
  into a false safety claim.
- Reusing generic host-wide `telemetry.stale`: one member can disappear while
  the rest of the thermal domain remains current.
- Correlating any SMART warning with any missing temperature: cross-drive
  evidence can create a false shared cause. Exact device or bay intersection is
  required.
- Clearing on one restored sample: transient recovery is not sustained
  coverage. Three complete identity-stable observations are required.
- Adding Prometheus, Zabbix, or Alertmanager: useful architectures, excessive
  service/dependency/security weight for this in-process contract.
- Starting a new `smartctl` subprocess: duplicates existing collection and
  expands device-access and command-injection review surface.
- Inferring Bay 3 from slot order: physical identity is never guessed.

### Collaboration opportunity

The strongest external conversation is with smartmontools and Prometheus
exporter maintainers about an identity-stable convention for distinguishing
"device present but temperature unavailable" from "device absent" and
"collector failed." That convention could save TruePanel and other NAS tools
from bespoke missing-series joins. No external contact was made.

## Open risks and next gate

- The present-member inventory and temperature records can still be captured at
  slightly different instants; the three-observation verifier reduces but does
  not eliminate race risk.
- Device names are runtime addresses. Exact physical bay strengthens the join,
  but a future stable WWN/ZFS-GUID migration should replace device-only matches.
- The five-case deterministic corpus is not a production false-positive rate.
- No live BattleStation data was read and no deployment occurred.

The strongest next step is independent review of the exact 9/9 candidate and
its preserved evidence. Only after that separate acceptance boundary should a
governed, read-only field snapshot prove the expected-member inventory contract
and measure whether three complete observations is the right recovery window.
Neither step may install this branch, run a new device query, or change storage.
