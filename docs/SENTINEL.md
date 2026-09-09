# Project SENTINEL

Project SENTINEL is TruePanel's deterministic operational-intelligence layer.
Its job is to connect evidence TruePanel already observes, show what that
evidence can affect, and give Mission Control and Flight Director a structured
explanation without turning inference into fact.

> **TruePanel does not just monitor the NAS. It understands what the available
> evidence says, shows what may be affected, and keeps unknowns visible.**

SENTINEL is under active development. The foundation described here is
read-only and has **no control authority**.

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
- Which applications or recent cargo rely on the affected storage?
- Which statements are confirmed, rejected, or still unknown?
- Which exact observation supports each statement?

## Foundation contract

The first SENTINEL slice lives in `truepanel.sentinel` and contains three
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
observed disk can lead to its vdev, then its pool, and a pool can lead to cargo
whose current path proves that it is stored on that pool. `blast_radius()`
performs bounded, cycle-safe downstream traversal over those proved edges.

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

## Current live-evidence adapter

`build_sentinel_snapshot()` accepts the existing Mission Control status shape
and currently understands a deliberately small, useful subset:

- system identity;
- storage pools;
- storage device, bay, vdev, and pool relationships;
- actionable SMART evidence;
- Cargo Bay Sonarr/Radarr items;
- current Cargo Bay paths that prove a pool-to-cargo relationship;
- whether independent Cargo Bay backup evidence is available.

The returned payload is explicitly:

```json
{
  "schema_version": 1,
  "read_only": true,
  "control_authority": false,
  "graph": {},
  "assessment": {}
}
```

This adapter performs no I/O. It consumes evidence that another TruePanel
component has already collected.

## Safety invariants

SENTINEL foundation work must preserve all of these invariants:

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

## Planned slices

The next useful increments are intentionally evidence-first:

1. **Storage topology adapter**: strengthen disk -> bay -> vdev -> pool ->
   dataset relationships with explicit provenance from current TrueNAS and
   enclosure evidence.
2. **Service consequence map**: connect datasets and mount paths to known
   applications/services without assuming ownership from names alone.
3. **Flight Director contract**: expose confirmed facts, rejected hypotheses,
   unknowns, blast radius, and recovery references as a structured explanation.
4. **HoloDeck SENTINEL scenario**: inject a deterministic disk fault and verify
   that SENTINEL identifies the physical/storage/application consequence chain
   while preserving unrelated services as unaffected or unknown.
5. **Mission Control presentation**: provide a compact operator explanation with
   drill-down provenance, keeping mobile usability intact.

The long-term product goal is not another monitoring dashboard. It is a NAS
flight computer whose explanations can be traced back to evidence.
