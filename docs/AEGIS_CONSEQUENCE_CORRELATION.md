# AEGIS consequence-aware incident correlation

Reviewed 2026-09-14 against accepted `main` at `f4ef8fda`. Stable-identity
follow-up details are in `docs/AEGIS_STABLE_CONSEQUENCE_IDENTITY.md`.

## Outcome

AEGIS can now add proved dependency reach to a storage incident when, and only
when, one detector-proved device and one read-only SENTINEL explanation resolve
to the same trusted Lifeline identity. The context describes what is reachable through proved graph
edges. It never reclassifies a running application as failed and never raises
the diagnostic confidence of AEGIS's probable-cause hypothesis.

The adapter consumes the SENTINEL object already present in the shared Mission
Control snapshot. It creates no poller, query, graph edge, recovery action, or
control path.

## Contract

- One incident device and one shared, unambiguous Lifeline identity are required.
- Every displayed path must begin at `disk:<exact device>`, end at its declared
  node, and contain a valid positive depth.
- Missing identity, multiple devices, duplicate explanations, malformed paths,
  or missing read-only boundaries produce `HOLD`.
- Consequence context reports `confidence_effect: none`.
- Mission Control says **proved dependency reach**, never “outage” or
  “unaffected.”
- The existing Recovery Coverage Matrix remains authoritative for actionable
  recovery guidance; this projection adds context, not a new alert.

## HoloDeck evidence

The deterministic scenarios prove six reachable objects even when `/dev/sdc`
becomes `/dev/sda`: the RAIDZ
VDEV, HDDs pool, Movies dataset, running Radarr application, one cargo item,
and verified backup evidence. Missing identity, cloned identity, reused device
path, and malformed graph paths hold closed.

- 6 scenarios: 2 `PROVED`, 4 `HOLD`
- path reassignments preserved: 1
- cloned-identity and reused-path holds: 1 each
- false joins: 0
- diagnostic confidence: 0.62 before and 0.62 after
- additional telemetry reads: 0
- recovery actions: 0
- control authority: false
- evidence: `docs/evidence/aegis-consequence-correlation-v1.json`

## Prior-Art Field Report

| Candidate | What the inspected code/docs supply | Maturity / fit / weight | License and recommendation |
| --- | --- | --- | --- |
| [OpenTelemetry Service Graph connector](https://github.com/open-telemetry/opentelemetry-collector-contrib/tree/main/connector/servicegraphconnector) | Pairs both sides of trace edges, makes unpaired/dropped evidence measurable, and emits explicit client/server relationships. | Active CNCF ecosystem and code coverage, but the connector is alpha, Go-based, trace-centric, and much heavier than TruePanel's local graph. | Apache-2.0. Adapt the explicit-edge and missing-pair semantics; do not embed the collector. |
| [Prometheus Alertmanager](https://github.com/prometheus/alertmanager) | Production grouping, deduplication, routing, and inhibition; its configuration warns that absent grouping labels can accidentally compare equal. | Mature, actively maintained, tested, and operationally proven; it solves notification correlation, not dependency proof. | Apache-2.0. Keep AEGIS's existing semantic adaptation; no runtime dependency. |
| [Kubernetes dependency graph builder](https://github.com/kubernetes/kubernetes/blob/master/pkg/controller/garbagecollector/graph_builder.go) | Maintains a UID-keyed dependency graph from observed events and isolates graph updates in one serialized processor. | Very mature and well tested, but far too large and Kubernetes-specific. | Apache-2.0. Adapt stable identity and explicit-edge discipline only. |
| [Salesforce PyRCA](https://github.com/salesforce/PyRCA) | Metric RCA algorithms, Bayesian/random-walk graph analysis, causal discovery, domain constraints, and benchmarks. | Useful future benchmark when a diverse field corpus exists; current package pulls NumPy, pandas, scikit-learn, NetworkX, matplotlib, JPype and more. Its learned graph would be weaker than current proved hardware paths for this increment. | BSD-3-Clause with notice obligations. Defer behind a replaceable offline benchmark; do not add to runtime. |
| [Grafana Tempo service graphs](https://github.com/grafana/tempo/tree/main/modules/generator/processor/servicegraphs) | Actual implementation shows bounded edge stores, dropped-edge metrics, semantic-convention compatibility, and explicit virtual nodes. | Mature project, but network-trace-specific and a large Go service. | AGPL-3.0. Architectural inspiration only; no code copied or linked. |

### Build versus adopt

Build the small TruePanel-owned adapter. Existing systems either group alerts
without proving hardware-to-workload reach, infer graphs from distributed
traces, or introduce a large statistical/runtime dependency. SENTINEL already
has the higher-quality local evidence. The legitimate shortcut is to reuse its
proved graph in the existing snapshot and borrow the ecosystem's identity,
edge, missing-pair, and bounded-store lessons.

No external code, dependency, schema, service, credential, or dataset was
incorporated. The implementation is original MIT-licensed TruePanel code; the
links above record architectural provenance and license boundaries.

### Rejected paths and weak assumptions

- Device basename, bay number, title, pool, or fuzzy string matching: rejected
  because they can bind the wrong physical source.
- Treating dependency reach as service failure: rejected; Radarr remains
  explicitly `RUNNING` in the positive scenario.
- Increasing root-cause confidence because the graph shows consequences:
  rejected as circular reasoning. Consequence and diagnosis evidence remain
  separate.
- Adding OpenTelemetry, PyRCA, NetworkX, or a second dashboard poller: rejected
  for this increment because each adds weight without improving the exact
  evidence already available.
- Copying Tempo's service-graph implementation: rejected because AGPL-3.0 is
  not suitable for incorporation into this MIT codebase.

### Most promising collaboration

The OpenTelemetry Service Graph maintainers—currently listed in the inspected
component documentation as `@mapno` and `@JaredTan95`—are the best people for JT
to approach about conventions for explicit, missing, and virtual dependency
edges. The conversation should focus on semantics and interoperability, not on
embedding the alpha connector.

## Open risks and next step

Lifeline identity must already be present in the shared snapshot; absence holds
closed. The next increment should make identity coverage explicit in the
Recovery Coverage Matrix and rehearse serial-model to WWN or ZFS-GUID migration
without splitting one incident or merging two drives.
