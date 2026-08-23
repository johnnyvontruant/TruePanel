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

## BattleStation Gate 0C

Gate 0C re-ran the corrected model against the same live degraded RAIDZ1 condition from the updated Lifeline head.

Observed corrected evidence:

- `member_id` preserved as `15571478626791065431`
- `historical_path` preserved as `/dev/disk/by-partuuid/389d5fd4-8899-434f-b171-ef29d8937033`
- `device` correctly remained null because no current Linux block device could be proven
- `physical_bay` correctly remained null
- remaining RAIDZ1 redundancy remained `0`
- generic operator guidance phase was `identify`
- persistent Lifeline repair-session phase was also `identify`
- member-identity and redundancy gates were satisfied
- physical-identity gate remained unsatisfied
- `can_identify_bay` remained false
- `can_begin_physical_service` remained false
- `can_execute_replacement` remained false
- active scrub telemetry was observed without intervention

The controlled test also proved the configuration-context finding directly:

- deployed `hardware.topology.front_bays` was empty
- repository checkout `hardware.topology.front_bays` contained the commissioned serial overrides for Bays 5 and 6

Production guards remained unchanged across the Gate 0C run:

- deployed configuration SHA unchanged
- LCD service PID unchanged
- Mission Control service PID unchanged

Gate 0C: PASS.

## BattleStation Gate 0D-R

Gate 0D-R collected read-only Linux, udev, SMART, PCI/SATA, by-path, and enclosure evidence to determine whether the disks previously commissioned as Bays 5 and 6 could be independently derived from the enclosure topology.

Observed disk paths:

- `sda` serial `WKD3MW7K`, HCTL `0:0:0:0`, `ID_PATH=pci-0000:00:1f.2-ata-1.0`
- `sdb` serial `WKD3MW4K`, HCTL `1:0:0:0`, `ID_PATH=pci-0000:00:1f.2-ata-2.0`
- `sde` serial `WKD3MW0D`, HCTL `3:0:0:0`, `ID_PATH=pci-0000:00:1f.2-ata-4.0`
- `sdd` serial `WSD9KX4V`, HCTL `8:0:0:0`, `ID_PATH=pci-0000:7b:00.0-ata-2.0`, WWN `0x5000c500e6494082`
- `sdf` serial `WSD9QAWH`, HCTL `12:0:0:0`, `ID_PATH=pci-0000:7c:00.0-ata-2.0`, WWN `0x5000c500e649d14a`

The enclosure object independently correlated:

- Slot 00 -> `sda`
- Slot 01 -> `sdb`
- Slot 03 -> `sde`

The enclosure object did not expose block-device links for Slots 02, 04, or 05. `sdd` and `sdf` are visible through separate PCI/SATA controller paths and therefore have no independent enclosure-path correlation on this host.

This establishes an important provenance distinction:

- Bays 1, 2, and 4 can be classified as kernel/enclosure-derived mappings.
- The mappings previously commissioned for Bays 5 and 6 cannot be claimed as enclosure-derived on BattleStation.
- `sdd` and `sdf` do have durable hardware identities through serial, WWN, HCTL, and PCI/SATA by-path values.
- Any Bay 5/6 mapping must remain an explicitly commissioned/configured mapping unless a separate model-specific physical-controller relationship is independently verified.

The Gate 0D-R collection also confirmed the production configuration and service PIDs were unchanged and the shell PATH remained intact after correcting the diagnostic harness.

Gate 0D-R: PASS.

### Safety disposition

Gate 0B: PASS.

Gate 0C: PASS.

Gate 0D-R: PASS.

Physical-control ladder: HOLD while the scrub is active and until deployed topology configuration is reconciled and independently verified.

No pool member was offlined, replaced, wiped, removed, or otherwise mutated during these tests.
