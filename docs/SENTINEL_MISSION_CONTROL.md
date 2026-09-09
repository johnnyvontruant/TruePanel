# SENTINEL in Mission Control

Mission Control can present Project SENTINEL's deterministic Flight Director
explanations directly from the shared status snapshot.

This presentation is deliberately downstream of the evidence engine. The web
interface does not create impact relationships, infer missing topology, classify
objects as unaffected, or gain recovery authority.

## Live snapshot contract

`SentinelSnapshotService` builds the existing SENTINEL graph and assessment,
then converts each current `impact_report` into the incident-package shape
accepted by `build_flight_director_explanation()`.

The resulting explanations are attached at:

```text
sentinel.explanations[]
```

Each explanation retains the established contract:

- `read_only: true`
- `control_authority: false`
- a deterministic source device
- confirmed known-impact objects
- exact proved graph paths
- verified independent-backup evidence only when its state is `VERIFIED`
- explicit unknowns
- the permanent language guard around objects outside the proved blast radius
- no recovery execution authority

Explanations are sorted by source device and source-node identity before
rendering so equivalent evidence produces stable operator presentation.

## Standby is not all clear

An empty `sentinel.explanations` list means SENTINEL has no active impact report
to explain. Mission Control renders this as **STANDBY**.

STANDBY must never be interpreted or worded as:

- the system is healthy;
- all storage is safe;
- no incident exists;
- all services are unaffected.

Those statements require their own deterministic evidence. The card therefore
states explicitly that standby is not an all-clear assertion.

## Mission Control card

The Glass Cockpit asset adds a full-width **SENTINEL / Flight Director** card
immediately beneath the situation summary. It uses the same shared
`truepanel:status` event as the rest of Mission Control, so it does not create a
second polling path.

For every active explanation the compact surface shows:

- explanation state;
- Flight Director headline and summary;
- count of proved downstream objects;
- count of reachable verified backup observations;
- count of explicit unknowns.

A native `details` disclosure exposes the evidence layer without crowding the
normal cockpit view. The drawer includes each known-impact object, its observed
state, the exact graph path used as provenance, verified backup evidence, and
all current unknowns.

The presentation intentionally does not provide an Execute, Repair, Replace, or
Apply control. SENTINEL v1 explains evidence; it does not actuate recovery.

## Mobile behavior

The card is part of the existing responsive Glass Cockpit asset rather than a
separate desktop-only dashboard. At narrow widths:

- the explanation lead collapses to one column;
- evidence counters reflow from three columns to one where needed;
- provenance paths wrap rather than force horizontal page scrolling;
- disclosure summaries retain a minimum 44-pixel touch target;
- no fixed-width panel is introduced.

Phone usability remains a release constraint for future SENTINEL presentation
work.

## Failure behavior

If TrueNAS topology evidence is unavailable, the existing fail-closed topology
unknown is preserved and carried into every live explanation that can still be
built from a partial proved path.

If SENTINEL itself cannot produce a deterministic assessment, the status payload
contains an unavailable SENTINEL object with an explicit unknown and an empty
`explanations` list. Mission Control remains available.

## Future presentation layers

A future local or external language model may rephrase these deterministic
explanations for conversational use, but it must remain downstream of this
contract. It may not:

- create a graph edge;
- suppress an unknown;
- upgrade confidence;
- convert absence from a blast radius into proof of no impact;
- classify backup protection without verified evidence;
- acquire or exercise recovery authority.

The deterministic snapshot remains the source of truth.
