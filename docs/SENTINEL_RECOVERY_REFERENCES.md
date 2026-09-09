# SENTINEL recovery references

Project SENTINEL can link a live storage explanation to an existing Pathfinder
recovery contract without acquiring recovery authority.

The link is intentionally narrow. SENTINEL does not select a repair procedure by
matching a title, bay number, pool name, severity, or other circumstantial
similarity. A reference exists only when the decorated Pathfinder recovery
contract contains a device identity that exactly matches the SENTINEL
explanation's source device.

## Contract

A linked explanation retains:

```text
recovery.available = true
recovery.authority = false
```

and contains one or more `recovery.references` entries. A reference includes:

- the Pathfinder incident and guidance-code identity;
- the exact SENTINEL source device used for the join;
- the existing guidance title, severity, and explanation;
- the passive verification strategy and current verification status;
- the existing action gate and its blockers;
- `authority: false`.

The reference deliberately omits mutable Pathfinder workflow state. The final
HTTP composition layer may advance workflow bookkeeping after the underlying
snapshot has been built. SENTINEL therefore links the stable procedure identity
and evidence gate, not a potentially stale workflow phase.

## Fail-closed identity rules

A reference is absent when any of these conditions is true:

- the SENTINEL explanation has no source device;
- the recovery contract has no device identity;
- the recovery device does not exactly equal the SENTINEL source device;
- runtime guidance evidence contains a different device than the recovery
  contract;
- the Pathfinder incident ID or guidance code is absent.

No fallback matching is attempted.

For example, a critical guidance card mentioning Bay 3 cannot be attached to
`/dev/sdc` merely because SENTINEL also localized `/dev/sdc` to Bay 3. The
Pathfinder recovery evidence itself must identify `/dev/sdc`.

## Mission Control presentation

The SENTINEL Flight Director evidence drawer shows recovery references beneath
known impact and verified backup evidence. The presentation displays:

- guidance title and code;
- severity;
- verification strategy and status;
- whether physical service is currently ready;
- whether destructive actions are currently ready;
- current action-gate blockers.

The card labels the section **Reference only · no repair authority** and exposes
no Execute, Repair, Replace, or Apply control.

Pathfinder's existing workflow remains the authority for its own bookkeeping.
Hardware and storage safety gates remain independent. SENTINEL merely points to
the matching procedure that TruePanel already knows about.

## Safety invariants

1. A recovery reference is not a recommendation to execute an action.
2. Reference availability never changes `control_authority`.
3. SENTINEL never widens Pathfinder's action gate.
4. SENTINEL never changes verification status.
5. Device identity conflicts fail closed.
6. Missing references remain unavailable rather than being guessed.
7. The Mission Control card remains read-only even when a reference is present.

This keeps the product promise clean: SENTINEL may explain what TruePanel can
prove and point to an evidence-matched recovery path, while existing safety
systems retain authority over what may happen next.
