# SENTINEL Flight Director Explanation Contract

SENTINEL's Flight Director explanation layer turns a deterministic incident
package into bounded operator language. It is a presentation contract over
proved evidence, not a new evidence producer.

The v1 implementation lives in `truepanel.sentinel.explanation` and remains
read-only with `control_authority: false`.

## Contract

`build_flight_director_explanation()` consumes a SENTINEL `incident_package`
containing a localized source device, proved downstream graph paths, backup
evidence, and explicit unknowns.

The output contains:

- a deterministic headline and summary;
- `confirmed_facts`, each backed by its exact proved graph path;
- `known_impact`, sorted by traversal depth and stable node identity;
- `protected_items` only when reachable backup evidence is explicitly
  `VERIFIED`;
- first-class `unknowns`;
- a permanent language guard that prevents absence from the graph from being
  described as proof that an object is unaffected;
- a recovery section that is unavailable and has no authority in v1.

## Language boundary

The most important v1 rule is intentionally narrow:

> **Not proved affected is not the same as proved unaffected.**

If Plex does not appear in the proved blast radius from a failed HDD, Flight
Director may say that Plex is not present in the proved blast radius. It may not
say that Plex is unaffected unless a future evidence provider can prove that
negative claim.

The same rule applies to backup state. Backup evidence with a state other than
`VERIFIED` does not become an `unprotected` claim. It remains unknown or simply
unconfirmed.

## Fail-closed behavior

An explanation enters `HOLD` rather than repairing or guessing evidence when:

- the incident source device is missing;
- no valid proved downstream path is present;
- an impact record has no node identity, kind, valid depth, or graph path.

Malformed impact records are discarded. The explanation does not synthesize a
replacement path from labels, names, or adjacent records.

## Determinism

Impact objects are ordered by traversal depth and node identity. Unknowns are
normalized and sorted. Equivalent incident packages therefore produce the same
structured explanation even when input list order changes.

This property makes Flight Director explanations suitable for CI snapshots,
HoloDeck rehearsals, regression testing, and future Mission Control rendering.

## Recovery authority

Explanation v1 deliberately does **not** select or execute recovery procedures.
Its recovery contract is:

```json
{
  "available": false,
  "authority": false,
  "reason": "Flight Director explanation v1 does not infer or execute a recovery procedure."
}
```

A later slice may attach Pathfinder or Lifeline recovery references when that
relationship can be proved deterministically. Selection and execution authority
remain separate concerns.

## Future presentation layers

Mission Control, a local language model, or another conversational interface may
render this payload in friendlier prose later. Those layers must remain
downstream of the deterministic contract. They may rephrase proved facts but
must not create new facts, suppress unknowns, upgrade confidence, or acquire
control authority.

That separation is the core SENTINEL product promise: the prose can become
smarter and more natural without making the source of truth probabilistic.
