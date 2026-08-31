# Project CHECKRIDE

Project CHECKRIDE turns a verified storage incident into an incident-bound,
read-only recovery flight plan. It composes AEGIS correlation, ORACLE evidence,
Lifeline identity, Pathfinder recovery criteria, and deterministic HoloDeck
branches without gaining storage or hardware authority.

## Current field case

The first case is an active SMART incident whose passive evidence identifies
bay 3, device `sda`, model `ST8000NE001-2M71`, serial suffix `MW6D`, pool
`HDDs`, and VDEV `raidz1-0`. Raw counters show substantial reallocated,
pending, offline-uncorrectable, and reported-uncorrect sectors while the drive
self-assessment says `PASSED` and ZFS says `ONLINE`.

Those facts support a live diagnosis. They do not prove that physical service
is ready or that a repair will succeed.

## Truth and authority boundaries

- The plan binds to the exact active incident ID. A mismatched or absent ID
  cannot render as operational Flight Director guidance.
- Missing bay, device, model, serial suffix, pool, VDEV, topology, redundancy,
  backup, or replacement facts remain explicit gaps.
- Conversation history is not machine telemetry. Backup health remains an
  operator-confirmation gate until it enters through a governed workflow.
- `physical_service_ready` and `destructive_actions_ready` remain false.
- CHECKRIDE never offlines, removes, replaces, wipes, labels, or actuates a
  drive or bay.
- Live diagnosis is not presented as a field-validated repair outcome.

## Deterministic rehearsal branches

HoloDeck covers six recovery branches:

1. Correct identity and replacement fit: proceed to operator review.
2. Wrong bay or serial: abort.
3. Undersized or already-in-use replacement: abort.
4. Degraded pool or unconfirmed backup: hold.
5. Healthy resilver progression: observe.
6. Stalled resilver or new errors: hold and escalate.

## Repair verification signature

A repair can be marked verified only after passive evidence proves all of the
following:

- the replacement identity differs from the failed identity;
- the replacement occupies the intended pool and VDEV;
- the resilver completes without problem evidence;
- the pool returns to `ONLINE`; and
- the triggering SMART incident remains absent during the reviewed window.

Until an external repair occurs, the signature state is
`awaiting_external_repair`.

## Reproduction

```bash
pytest -q tests/test_checkride.py tests/test_flight_director.py tests/test_aegis.py
node --check truepanel/web/static/reliability-view.js
node --check truepanel/web/static/glass-cockpit.js
python -m truepanel.hangar validate --root .
```

## Remaining exit gate

The software composition and simulated branches can be validated without live
mutation. The HANGAR experiment remains `IN_PROGRESS` until an operator obtains
a suitable replacement, reconfirms backup and identity evidence immediately
before service, completes the external repair, and captures a passing or
evidence-backed failing verification signature.
