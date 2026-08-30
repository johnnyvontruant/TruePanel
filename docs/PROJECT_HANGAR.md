# Project HANGAR

HANGAR is TruePanel's permanent experiment memory. Its canonical source is
`truepanel/hangar/registry.json`; the four pages under `docs/hangar/` are generated
views, so an experiment changes state without moving its dossier or breaking links.

## The four boxes

- `FUTURE`: a testable hypothesis and value proposition, not an unbounded wish.
- `IN_PROGRESS`: a branch, next test, and explicit exit criteria.
- `COMPLETED`: a conclusion backed by digest-bound, reproducible evidence.
- `FAILED`: an evidence-backed failure mode and a lesson worth carrying forward.

These are the only primary states. Architecture decisions, operator manuals, prior-art
reports, and generated evidence remain distinct document kinds and are linked from a
dossier instead of being relabeled as experiments.

## Dossier contract

Every stable `TP-EXP-NNNN` record carries its hypothesis, value, prior art, safety
class, development references, protocol, fixtures, success and abort criteria,
evidence paths and SHA-256 hashes, outcome, invalidated assumptions, reproduction,
revisit conditions, strongest follow-up, and freshness dates. HANGAR never turns a
lab result into field validation and grants no operational authority.

## Contributor workflow

1. Copy `docs/hangar/EXPERIMENT_TEMPLATE.json` into the registry and assign the next
   stable ID. IDs are never recycled.
2. Put the experiment in exactly one primary state and satisfy that state's contract.
3. Preserve evidence in its natural project location. Link it and record its byte-level
   SHA-256 rather than moving it into a HANGAR-specific pile.
4. Validate with `python -m truepanel.hangar validate --root .`.
5. Regenerate all views with `python -m truepanel.hangar render` and commit them with
   the registry change.
6. Review freshness dates. Stale does not mean invalid; it means the conclusion needs
   an explicit human look before new work relies on it.

The validator rejects duplicate or unstable IDs, unknown states, missing dossier
fields, broken evidence paths, digest drift, and weak state-specific records.

## Flight Director relationship

The first Flight Director proof is `TP-EXP-0013`. Its deterministic runner replays the
fan-degradation incident through ORACLE and AEGIS, labels unknown topology rather than
guessing, forecasts the fixture's thermal envelope, rehearses three safe branches, and
compares restored-airflow evidence with a repair signature. The preserved summary is
`docs/evidence/flight-director-shared-cooling-v1.json`.

