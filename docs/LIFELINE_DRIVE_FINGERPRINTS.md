# Lifeline last-known-good drive fingerprints

Project Lifeline keeps a metadata-only memory of independently verified healthy drive identity so a future missing-member incident can be reconstructed without guessing from Linux device names or empty enclosure slots.

## What is recorded

A fingerprint is accepted only when healthy ZFS and hardware observations agree on the same live front-bay leaf. The stored record may include:

- pool and VDEV identity
- stable ZFS member GUID
- partition PARTUUID
- current ZFS path and Linux whole-disk name
- physical bay and mapping source
- enclosure identity
- drive model
- full serial and serial suffix
- WWN when available
- exact byte capacity
- first/last healthy observation timestamps

Current Linux device names are intentionally treated as transient. A drive may move from `sdg` to another `sdX` name without invalidating its fingerprint when the stable identity fields still agree.

## Verification contract

The production provider cross-checks two read-only ZFS views:

1. `zpool status -L -P` for the live absolute leaf path.
2. `zpool status -g -L -P` for the stable leaf GUID.

The two status trees must have matching structure, states, and error counters. The live leaf is then joined to TruePanel's storage inventory and udev metadata.

A fingerprint is marked verified only when:

- the pool and leaf are `ONLINE`
- no scrub/resilver recovery is active
- the live ZFS path resolves to an attached front-bay disk
- the bay mapping source is trusted (`kernel` in the current implementation)
- serial identity is present
- capacity is a positive exact byte count
- the partition has a PARTUUID

WWN is retained when the platform exposes one but is not required on systems that do not publish it.

## Conflict behavior

Stable identity is never silently overwritten. If the same pool/member GUID is later observed with conflicting PARTUUID, serial, WWN, model, capacity, bay, or trusted mapping source, the existing fingerprint is marked `conflicted`.

Conflicted fingerprints are not returned for automatic Lifeline commissioning.

Linux device path changes alone are not conflicts.

## Repair-session handoff

When a future fault reports a missing ZFS member GUID, Mission Control may consult the last-known-good fingerprint store.

Automatic handoff requires the stored pool/member GUID to match the immutable original fault. When the fault carries a historical PARTUUID path, that PARTUUID must also match the fingerprint. Current device identity must be absent.

If those checks pass, Lifeline can populate its existing metadata-only historical provenance fields with:

- verified physical bay + serial suffix
- verified historical capacity + model

The immutable `original_fault` is not rewritten. The repair evaluation receives a derived historical identity, while storage execution authority remains absent.

## HoloDeck isolation

HoloDeck injects a no-host-I/O fingerprint provider and places fingerprint/session ledgers inside its temporary runtime directory. Simulation must never execute host `zpool`, udev, enclosure, or protected-path reads as a side effect of drive fingerprinting.

## Privacy

The fingerprint ledger is local operational metadata and is written mode `0600`. Full serial and WWN values are intentionally not exposed in the public Lifeline summary; Mission Control publishes only a count/conflict summary.

Compatibility support bundles remain privacy-safe and reject serial, WWID, and WWN keys.

## BattleStation commissioning origin

This feature was motivated by a live TVS-671 incident in which a missing RAIDZ1 member later returned after Bay 3 was reseated. The restored leaf independently proved the same ZFS member GUID, PARTUUID, physical Bay 3 mapping, drive serial, WWN, model, and exact byte capacity. That incident demonstrated that retaining the same evidence while a drive is healthy can remove a large amount of forensic work from the next recovery.

The implementation remains planning-only. It does not offline, replace, wipe, partition, label, or otherwise mutate storage.
