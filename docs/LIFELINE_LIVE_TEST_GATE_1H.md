# Project Lifeline Live Test: Gate 1H

Date: 2026-08-23 (America/Phoenix)

Host: BattleStation, QNAP TVS-671 running TrueNAS SCALE.

Gate 1H certified the new last-known-good drive fingerprint path against the restored healthy `HDDs` RAIDZ1 using read-only host observations and temporary metadata ledgers only.

## Safety boundary

Gate 1H performed no disk insertion/removal/reseat, no bay LED action, no service restart, no production configuration change, and no ZFS/storage mutation.

The real pool was required to be `ONLINE`, free of scrub/resilver activity, and reporting no known data errors before the fingerprint probe ran.

## Live healthy capture

The fingerprint provider correlated the healthy ZFS path view, GUID view, kernel storage inventory, and udev metadata.

Four front-bay members had independently trusted `kernel` mappings and were recorded. No mapping was invented for bays not independently resolved.

The restored Bay 3 member was verified as:

- pool: `HDDs`
- member GUID: `15571478626791065431`
- PARTUUID: `389d5fd4-8899-434f-b171-ef29d8937033`
- current observational Linux device: `sdg` / `/dev/sdg1`
- physical bay: `3`
- mapping source: `kernel`
- serial: `WKD3MW6D`
- serial suffix: `MW6D`
- WWN: `0x5000c500cd3caaae`
- model: `ST8000NE001-2M71`
- exact capacity: `8001563222016` bytes

The temporary fingerprint ledger was written mode `0600`. Public Lifeline status exposed only fingerprint count/conflict summary rather than full serial/WWN payloads.

## Memory-only disappearance simulation

A separate simulated fault reproduced the earlier BattleStation missing-member shape for the same GUID and historical PARTUUID while providing no current Linux device, bay, serial, model, or capacity.

Lifeline automatically recovered from the last-known-good fingerprint:

- physical Bay 3
- serial suffix `MW6D`
- exact capacity `8001563222016` bytes
- historical model provenance

The immutable `original_fault` remained unchanged with `device=None`, `bay=None`, `serial_last4=None`, and `capacity_bytes=None`.

The repair evaluation advanced to `prepare` with `can_identify_bay=true`, while physical service remained blocked by backup acknowledgement and replacement-media gates. `write_preconditions_complete` and `can_execute_replacement` remained false.

## Negative identity control

The same member GUID paired with a different historical PARTUUID was rejected. The fingerprint did not supply a bay or capacity across that identity conflict.

## Production and storage guards

Production TruePanel configuration hash and service PIDs were unchanged after the test.

The real `HDDs` pool remained `ONLINE`, retained all six members, and continued to report no known data errors.

Gate 1H: **PASS**.

## Next bounded gate

Gate 1I should prove the same metadata survives and is reusable across independent process lifetimes, approximating Mission Control/service restarts without touching production services or the storage pool.
