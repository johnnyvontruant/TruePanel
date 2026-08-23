# Project Lifeline Live Test Notes

## BattleStation Gate 0B

Date: 2026-08-22 (America/Phoenix)

Host: BattleStation, QNAP TVS-671 running TrueNAS SCALE.

### Baseline discovered before Lifeline deployment

The live HDDs pool was already DEGRADED before any Lifeline code was deployed.

Observed state:

- pool: `HDDs`
- topology: RAIDZ1
- one member: `UNAVAIL`
- historical member identity: ZFS GUID `15571478626791065431`
- historical path: `/dev/disk/by-partuuid/389d5fd4-8899-434f-b171-ef29d8937033`
- remaining redundancy: `0`
- surviving members: no ZFS READ/WRITE/CKSUM errors
- pool errors: no known data errors
- physical enclosure Slot 02 / human Bay 3 was empty
- the historical ZFS identity could not be independently joined to a current Linux block device

A scrub began during the live-test window. Hardware-control and deployment gates were therefore held while the scrub remained active.

### Shadow-mode result

Lifeline was executed from an isolated worktree against live, read-only BattleStation telemetry while production services remained untouched.

Gate 0B passed:

- real degraded RAIDZ1 detected
- unavailable member detected
- zero remaining redundancy detected
- scrub state observed read-only
- physical Bay 3 was not guessed
- repair session held at `identify`
- physical service remained locked
- replacement execution remained locked
- persistent metadata-only shadow session opened under `/tmp`
- production configuration hash did not change
- LCD service PID did not change
- Mission Control service PID did not change

### Live-driven correction

The first shadow run exposed a semantic bug: a historical path under `/dev/disk/by-partuuid/...` was being reduced to its basename and published as though it were a current Linux block-device name.

The implementation was corrected to keep these concepts separate:

- `member_id`: logical ZFS member identity
- `historical_path`: historical ZFS path evidence
- `device`: current Linux whole-device identity, only when independently resolvable
- `physical_bay`: current chassis identity, only when independently correlated

A missing ZFS member can therefore open a persistent Lifeline session using its logical member identity while `device` and `physical_bay` remain null. The repair stays in `identify` and cannot unlock physical service.

The BattleStation missing-member shape is now permanent automated regression coverage.

### Topology configuration finding

An apparent Bay 5/6 discrepancy was traced to configuration context rather than topology resolver code.

An earlier diagnostic was launched with `/root/TruePanel` as the current working directory, causing `load_config()` to read the repository checkout's `truepanel.yaml`, which includes configured serial mappings for Bays 5 and 6.

The controlled Gate 0B shadow process changed into the deployed root before hardware inventory resolution, causing it to read the actual deployed `truepanel.yaml`. In that configuration, Bay 5/6 overrides were not observed and the corresponding disks remained unassigned.

Before physical Lifeline controls are commissioned, the deployed configuration must be reconciled with the already-verified chassis topology. No configuration change should be made merely to satisfy Lifeline; the mapping must be independently confirmed first.

### Safety disposition

Gate 0B: PASS.

Physical-control ladder: HOLD while the scrub is active and until deployed topology configuration is reconciled.

No pool member was offlined, replaced, wiped, removed, or otherwise mutated during this test.
