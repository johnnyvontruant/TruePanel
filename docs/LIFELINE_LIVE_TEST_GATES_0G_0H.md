# Project Lifeline Live Test Notes: Gates 0G and 0H

Date: 2026-08-23 (America/Phoenix)

Host: BattleStation, QNAP TVS-671 running TrueNAS SCALE.

These gates were executed from the isolated Lifeline shadow worktree against the real degraded `HDDs` RAIDZ1 while production TruePanel services remained untouched. The pool scrub remained active during both gates, so no hardware-control, service-restart, configuration-promotion, or storage-write action was performed.

## Gate 0G: Replacement-discovery negative control

Gate 0G exercised `ReplacementCandidateProvider` against BattleStation's live block inventory while the failed ZFS member remained absent.

Observed discovery:

- surviving HDDs `sda`, `sdb`, `sde`, `sdd`, and `sdf` were visible to the replacement-discovery layer
- boot-media device `sdc` was excluded
- internal NVMe devices were excluded
- all five surviving HDDs were recognized as existing ZFS members
- all five surviving HDDs were recognized as containing preserved data
- every surviving HDD was rejected as replacement media with `replacement_belongs_to_pool` and `replacement_contains_preserved_data`
- no acceptable replacement candidate existed
- multiple visible invalid candidates collapsed to an ambiguous replacement assessment rather than one candidate being selected implicitly
- repair phase remained `identify`
- `can_prepare_replacement` remained false
- `can_execute_replacement` remained false

Production configuration hash and both TruePanel service PIDs remained unchanged.

Gate 0G: PASS.

## Gate 0H: Persistent session across independent processes

Gate 0H exercised the metadata-only Lifeline ledger across three separate Python process lifetimes while observing the same real ZFS fault.

Process 1 created the repair session:

- fault key: `drive:HDDs:raidz1-0:15571478626791065431`
- attempt: `1`
- one active session only
- original fault preserved the missing member GUID and historical PARTUUID path
- repair phase: `identify`
- physical service and storage execution remained locked

Process 2 cold-opened the ledger and added metadata-only operator state:

- backup-state acknowledgement persisted
- exact `qnap-tvs-x71` service provenance persisted
- source recorded as the QNAP TVS-x71 Series Hardware User Manual
- physical identity remained blocked
- repair phase remained `identify`

Process 3 cold-opened the ledger again and verified persistence invariants:

- same session ID survived
- attempt remained `1`
- no duplicate repair session was created
- `created_at` remained unchanged
- `original_fault` remained byte-for-byte equivalent to the checkpointed original fault
- metadata acknowledgement and service provenance survived the cold reopen
- healthy-observation count remained `0` while the fault persisted
- repair phase remained `identify`
- physical-service and replacement authority remained locked
- Lifeline ledger permissions were `0600`

The production configuration SHA, LCD service PID, and Mission Control service PID remained unchanged across the gate.

At the final Gate 0H observation, the scrub was still active but had reached 99.33%, with `0B repaired` and no known data errors.

Gate 0H: PASS.

## Safety disposition

Gates 0G and 0H extend the existing live-test evidence without changing the physical-control hold:

- no pool member was offlined, replaced, wiped, removed, or otherwise mutated
- no bay-identify LED was operated
- no spare disk was inserted
- no production TruePanel service was restarted
- no production TruePanel configuration was changed
- no Lifeline code was promoted into the live deployment

Physical-control testing remains held until the active scrub has completed and the next post-scrub readiness gate confirms a stable baseline.
