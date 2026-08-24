# Project Lifeline Live Test: Gate 1I

Date: 2026-08-23 (America/Phoenix)

Host: BattleStation, QNAP TVS-671 running TrueNAS SCALE.

Gate 1I certified last-known-good drive fingerprints across independent Python process lifetimes without restarting production services, moving hardware, or mutating ZFS.

## Preconditions

- `HDDs` was fully `ONLINE`.
- No scrub or resilver was active.
- ZFS reported no known data errors.
- Restored physical Bay 3 remained present with PARTUUID `389d5fd4-8899-434f-b171-ef29d8937033`.
- Production TruePanel configuration hash and both service PIDs were captured before the gate.

## Process 1: first healthy observation

A fresh Python process collected the real healthy drive fingerprints and persisted them to a temporary metadata ledger.

Bay 3 evidence:

- member GUID `15571478626791065431`
- PARTUUID `389d5fd4-8899-434f-b171-ef29d8937033`
- physical Bay 3
- serial `WKD3MW6D`
- WWN `0x5000c500cd3caaae`
- exact capacity `8001563222016` bytes
- trusted mapping source `kernel`

The fingerprint ledger was mode `0600` and recorded one healthy observation.

## Process 2: cold reopen and second observation

A second independent Python process cold-opened the ledger from disk, collected the live healthy fingerprint again, and merged the observation.

Results:

- observations advanced from `1` to `2`
- first-seen timestamp was preserved
- last-seen timestamp advanced
- current Linux path remained observational only (`sdg` / `/dev/sdg1`)
- stable GUID/PARTUUID/Bay/serial/WWN/capacity identity did not drift
- fingerprint remained non-conflicted

## Process 3: persisted memory only

A third independent Python process intentionally performed no live fingerprint collection. It cold-opened only the persisted ledger and simulated the prior BattleStation missing-member condition entirely in memory.

Lifeline automatically recovered:

- physical Bay 3
- serial suffix `MW6D`
- exact minimum capacity `8001563222016` bytes

The immutable original fault remained unchanged with current device, bay, serial suffix, and capacity absent.

Authority remained fail-closed:

- `can_identify_bay = true`
- `can_begin_physical_service = false`
- `write_preconditions_complete = false`
- `can_execute_replacement = false`

## Process 4: cloned-ledger identity conflict

A fourth independent process cloned the fingerprint ledger and modified only the clone with conflicting stable serial and WWN identity.

Results:

- cloned fingerprint was marked conflicted
- conflicted fingerprint lookup returned no automatic identity
- simulated missing member could not recover a bay or capacity from the conflicted clone
- `can_identify_bay = false`
- `can_execute_replacement = false`
- authoritative original fingerprint ledger remained usable

This proves stable identity conflict revokes automatic trust rather than overwriting prior evidence.

## Permission and production guards

All temporary fingerprint and session ledgers were mode `0600`.

Production guard after Gate 1I:

- deployed `truepanel.yaml` hash unchanged
- LCD service PID unchanged
- Mission Control PID unchanged
- no production service restart occurred

Real storage guard after Gate 1I:

- `HDDs` remained `ONLINE`
- all six RAIDZ1 members remained `ONLINE`
- no scrub/resilver became active
- no known data errors

## Result

Gate 1I: **PASS**.

Last-known-good drive identity is now certified as durable operational memory across process lifetimes. It can reconstruct the known physical target and exact historical capacity without consulting the absent drive, while conflicting stable hardware identity disables automatic reuse.

No hardware action, storage mutation, replacement execution, or storage-write authority was granted by this gate.
