# Lifeline Historical Identity Contract

Project Lifeline must continue to identify physical service targets after a failed disk is no longer present without ever guessing that an empty bay is the failed bay.

## BattleStation evidence

BattleStation live testing exposed the motivating case:

- `HDDs` is a RAIDZ1 pool with one missing member.
- The missing ZFS member is GUID `15571478626791065431`.
- ZFS preserves the historical path `/dev/disk/by-partuuid/389d5fd4-8899-434f-b171-ef29d8937033`.
- Current hardware inventory cannot resolve that historical path to a present Linux block device.
- The enclosure currently reports human Bay 3 empty, but emptiness alone is not proof of failed-member identity.

Historical TruePanel storage events independently preserve a stable hardware identity for the failed physical disk:

- serial `WKD3MW6D`
- physical Bay 3
- model `ST8000NE001-2M71`
- critical SMART state with persistent pending/offline-uncorrectable sectors
- changing Linux `/dev/sdX` names over time, demonstrating why device names are not stable identity

A prior BattleStation diagnostic also captured the complete historical relationship between the ZFS PARTUUID and serial `WKD3MW6D`. That archived operator evidence proves the real machine's Bay 3 identity for this incident, but a shipping Lifeline implementation must not depend on conversational history or an external operator transcript.

## Required persistent chain

Future Lifeline versions should persist a local, metadata-only storage identity ledger while members are still present. A usable historical proof should be able to retain:

1. pool identity
2. VDEV identity
3. stable ZFS member identity such as PARTUUID and/or ZFS GUID where available
4. current Linux whole-device identity at observation time
5. stable drive serial and WWN
6. independently resolved or commissioned physical bay
7. mapping source/provenance
8. observation timestamp and schema version

The durable relationship is therefore:

`ZFS member identity -> serial/WWN -> physical bay`

Linux `/dev/sdX` names are supporting observations only and must never be the durable key.

## Trust rules

Historical identity may satisfy a physical-identity gate only when all applicable conditions are true:

- the historical record was persisted while the source drive was present
- the record contains a stable ZFS identity and stable hardware identity
- the physical bay was independently resolved or explicitly commissioned at the time of observation
- the record is internally consistent and unambiguous
- a newer conflicting observation does not exist
- the current failed member matches the stored stable ZFS identity
- the current chassis/service profile still permits that physical-bay interpretation

Historical identity must fail closed when evidence is missing, duplicated, conflicting, stale beyond the policy contract, or only inferable from an empty slot.

## Safety boundary

Historical identity is identification evidence only. It must not grant storage-write authority.

Even when a historical physical bay is verified:

- `can_execute_replacement` remains false in Project Lifeline
- replacement media must still be independently discovered and validated
- model-specific chassis procedure provenance remains required
- backup-state acknowledgement remains separate
- active resilver/recovery state remains a hard service hold
- future storage mutations require a separately designed authority layer

## Live-test disposition

For the current BattleStation incident, the archived evidence is sufficient for humans to know that the missing member was the disk with serial `WKD3MW6D` in Bay 3. The current Lifeline build correctly remains at `identify` because that complete membership-to-hardware bridge is not yet available from its own persistent local state.

This is intentional fail-closed behavior, not a failure of the current repair state machine.
