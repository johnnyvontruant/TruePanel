# Project SENTINEL

Project SENTINEL is TruePanel's deterministic operational-intelligence layer.
Its job is to connect evidence TruePanel already observes, show what that
evidence can affect, and give Mission Control and Flight Director a structured
explanation without turning inference into fact.

> **TruePanel does not just monitor the NAS. It understands what the available
> evidence says, shows what may be affected, and keeps unknowns visible.**

SENTINEL is under active development. The current implementation is read-only
and has **no control authority**.

## Why SENTINEL exists

TruePanel already has strong specialized evidence producers:

- storage and SMART observations;
- physical bay and pool/vdev evidence;
- ORACLE baselines and drift;
- AEGIS correlation;
- Pathfinder and Lifeline recovery context;
- HoloDeck deterministic incident fixtures;
- Cargo Bay application-workflow and independent-backup evidence.

Those systems answer focused questions well. SENTINEL adds the missing system
model between them. It is designed to answer questions such as:

- What object is unhealthy?
- What downstream objects can the observed object affect?
- Which datasets and applications depend on the affected storage?
- Which recent cargo and independent-backup observations sit downstream?
- Which statements are confirmed, rejected, or still unknown?
- Which exact observation supports each statement?

## Foundation contract

The SENTINEL foundation lives in `truepanel.sentinel` and contains three core
layers.

### Evidence model

`EvidenceRef` records a source, stable reference, short summary, and optional
observation time. Evidence is carried by graph nodes, relationships, and
operator-facing claims so explanations remain inspectable.

### System knowledge graph

`KnowledgeGraph` relates typed objects including:

`hardware -> bay -> disk -> vdev -> pool -> dataset -> application -> service -> cargo -> backup evidence -> incident -> recovery`

Not every relationship is known on every machine. SENTINEL does **not** create
an edge merely because one would be convenient. Missing relationships remain
missing until a deterministic source proves them.

Edges are directed in the direction of possible consequence. For example, an
observed disk can lead to its vdev, then its pool, a pool can serve a dataset,
and a dataset can serve an application only when current TrueNAS middleware
evidence proves that dependency. `blast_radius()` performs bounded, cycle-safe
downstream traversal over those proved edges.

### Assessment contract

`SentinelClaim` classifies a statement as:

- `confirmed`
- `rejected`
- `unknown`

and gives it a bounded confidence plus the evidence that supports that
classification. Unknowns are first-class output rather than error text.

For example, Cargo Bay reporting `NOT_TRACKED` backup evidence does **not** let
SENTINEL claim that media is unprotected. The only valid conclusion is that
SENTINEL cannot currently determine whether that cargo is protected.

## Storage Intelligence v1

The first Storage Intelligence slice extends the graph beyond component health
into evidence-backed consequence mapping.

### TrueNAS topology evidence

`TopologyResolver` uses the supported TrueNAS `midclt` interface to read:

- `pool.dataset.query` for current dataset identity and mountpoints;
- `app.query` with application configuration retrieval for current application
  evidence.

The resolver does not classify an application from its name or description. It
recursively inspects the returned application payload only for literal paths
beginning with `/mnt/`. A dataset-to-application relationship exists only when
a literal path is contained by a dataset mountpoint.

When multiple datasets could contain the same path, the longest matching
mountpoint wins. This ties the dependency to the nearest dataset instead of
claiming every ancestor dataset as the application's direct dependency.

Topology observations are cached for 60 seconds by default to bound middleware
cost. The cache returns defensive copies so a consumer cannot mutate retained
evidence.

### Consequence chain

With sufficient evidence, SENTINEL can now assemble a chain such as:

`Bay 3 -> /dev/sdc -> raidz1-0 -> HDDs -> HDDs/Movies -> Radarr -> recent cargo -> backup evidence`

Each hop must come from an independent deterministic source:

- bay/disk/vdev/pool from current storage evidence;
- pool/dataset from TrueNAS dataset evidence;
- dataset/application from a literal TrueNAS application path;
- application/cargo from Cargo Bay's source identity;
- pool/cargo from the cargo item's current `/mnt/<pool>/...` path;
- cargo/backup evidence from exact current-path correlation in Cargo Bay.

The backup relationship is represented as `evidenced_by`. Backup evidence is an
observation about the cargo, not an assertion that the backup system itself is
a runtime dependency of the media.

### Impact reports

Actionable SMART observations now seed deterministic `impact_reports`. For each
SMART-affected disk that current topology can identify, SENTINEL traverses the
proved downstream graph and returns:

- the source disk;
- every known reachable object;
- each object's type, state, and label;
- traversal depth;
- the exact node path used to reach it.

`known_downstream_count` means exactly that. It is not a claim that the graph is
complete. If SMART evidence exists but the current storage topology cannot
identify the disk, SENTINEL emits an explicit unknown and produces no invented
blast radius.

### Mission Control integration

`SentinelSnapshotService` composes above the existing Mission Control snapshot
service. It attaches bounded `sentinel_topology` evidence and a deterministic
`sentinel` assessment without changing the established storage, Lifeline,
Cargo Bay, Pathfinder, or Flight Director contracts beneath it.

The production Mission Control launcher now supplies this composed snapshot
service to the existing server stack. Failure of the topology provider is
fail-closed: Mission Control remains available, topology is marked unavailable,
and SENTINEL reports what it cannot prove instead of fabricating dependencies.

The operator-facing Mission Control card is intentionally deferred until this
evidence contract has survived CI, HoloDeck scenarios, and live observation.

## Current payload

The returned SENTINEL payload is explicitly read-only:

```json
{
  "schema_version": 1,
  "read_only": true,
  "control_authority": false,
  "graph": {
    "nodes": [],
    "edges": []
  },
  "assessment": {
    "state": "CLEAR",
    "claims": [],
    "unknowns": []
  },
  "impact_reports": []
}
```

`build_sentinel_snapshot()` itself performs no I/O. Middleware reads are kept in
the separate topology provider and their normalized output becomes evidence
supplied to the deterministic adapter.

## Safety invariants

SENTINEL work must preserve all of these invariants:

1. **Read-only means read-only.** SENTINEL does not mutate storage, services,
   applications, hardware, or configuration.
2. **No inferred evidence.** A relationship without deterministic provenance is
   absent, not guessed.
3. **Unknown is a valid result.** Lack of backup evidence, topology evidence, or
   application mapping must not become a negative claim.
4. **Control authority stays separate.** SENTINEL may recommend a recovery path
   later, but it does not acquire the authority to execute it.
5. **Language is downstream of evidence.** A future conversational or local-AI
   presentation layer may explain SENTINEL output, but it must not be the source
   of truth.
6. **Traversal is bounded and cycle-safe.** A malformed or cyclic relationship
   cannot cause unbounded blast-radius calculation.
7. **Failure preserves the cockpit.** Loss of topology evidence must degrade
   SENTINEL to explicit unknowns rather than prevent Mission Control status from
   being served.

## Planned slices

The next useful increments remain evidence-first:

1. **HoloDeck SENTINEL scenario**: inject a deterministic disk fault and verify
   the complete storage/application/cargo consequence chain while preserving
   unrelated services as unaffected or unknown.
2. **Flight Director contract**: expose confirmed facts, rejected hypotheses,
   unknowns, blast radius, and recovery references as a structured explanation.
3. **Service consequence expansion**: add additional service and dataset
   relationship evidence only where TrueNAS or another deterministic provider
   can prove it.
4. **Mission Control presentation**: provide a compact operator explanation with
   drill-down provenance, keeping mobile usability intact.
5. **Optional language layer**: only after the deterministic contract is stable,
   allow a local or external presentation layer to turn SENTINEL facts into
   conversational explanations without granting it authority or truth-making
   power.

The long-term product goal is not another monitoring dashboard. It is a NAS
flight computer whose explanations can be traced back to evidence.
