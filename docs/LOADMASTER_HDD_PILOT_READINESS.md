# Loadmaster HDD Pilot Readiness (Operator-Acknowledged Degraded Pool)

## Scope

The operator has accepted proceeding with development of a constrained
real-library pilot despite the `HDDs` RAIDZ1 being DEGRADED.

**Acceptance of risk does not provide generic permission to delete, overwrite,
unmount or transfer files.** Those operations still need an exact cartridge,
source/destination scope, physical approval and a qualified RO watchdog.
A second RAIDZ1 disk failure could make the pool unrecoverable without an
independent backup. A clean scrub does not restore missing redundancy.

This checkpoint is deliberately a **read-only inventory survey**:
- Reads the existing registered cartridges and durable pending-cargo ledger.
- Restricts candidate sources to regular files under `/mnt/HDDs`.
- Selects up to three smallest candidates, individually <=4 GiB.
- Filters macOS/Windows housekeeping artifacts through the shared policy.
- Excludes Daria in every path (protected fan restoration).
- Rejects symlinked, missing, changed-size, unregistered, or deeper-than-
  two-component candidates.
- Reports the exact cartridge UUID, registered serial status, and whether backup permission is currently enabled (a disabled permission does not prevent a read-only survey).
- Reads pool status using `zpool list` but does not block the survey on
  `DEGRADED`. The output always reports degraded risk.
- Does not touch USB and does not calculate file hashes; hashes and device
  attestation belong to the next attended physical-pilot preflight.

## Run on BattleStation development checkout

```sh
cd /mnt/SSDs/Applications/TruePanel-Executor-Stage
python3 -m unittest discover -s tests -p 'test_loadmaster_hdd_pilot_candidates.py' -v
python3 -m tools.loadmaster_hdd_pilot_candidates
```

If no candidates are found, this is a clean HOLD, not approval to
read or copy arbitrary files. Do not use the synthetic spare as a substitute
for the registered production cartridge.

## Implementation status and remaining gates

The proven mixed-direction hardware actuator is still specifically constrained
to `/mnt/SSDs/` and the pinned disposable spare. It **must not** be launched
directly against `/mnt/HDDs`; changing the source scope and cartridge
identity requires a separate reviewed, tested host actuator integration.

The production pilot should be **NAS → USB first** with a single existing
small episode, a blank/noncolliding destination on the correct registered
cartridge, and an independent hash/receipt audit after write. USB → NAS
requires an additional explicit write-risk review since it mutates the
degraded source pool.

No production deployment, GPIO operation or mount changes occur at this stage.
