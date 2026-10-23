# Checkpoint 21: One-file TV N-Z host actuator qualification

## Deployment status

**STAGING ONLY until all BattleStation Linux regressions pass and operator
separately authorizes the physical live command.**

New host code is intentionally separate from the previously qualified
spare-drive runner. The spare guard remains pinned to the disposable spare.
The new TV N-Z code never relaxes the old SSD-only batch executor rule.

## Pinned operation

- From: `/mnt/HDDs/Shows/TV N-Z/Nobody Wants This (2024)/3x01 - It's Perfect.mkv`
- To: `/mnt/loadmaster-tv-nz-ro/TV N-Z/Nobody Wants This (2024)/3x01 - It's Perfect.mkv`
- 336388391 bytes, SHA-256:
  `c819a0d72cdb18c679824c687559847beb435747bb9f62c252eb906179c554ab`
- Cartridge: `tv-n-z`, UUID `6988-53EB`, serial `2532EA8D3DC7`.
- NAS -> USB only, no USB -> HDD.
- No overwrite, no delete, Daria/protected media excluded. No freeform path.

Physical backup approval is only from a **fresh real lower Copy-button press**
wired through the host GPIO service. The host requires exclusive ownership:
`truepanel.service` must be deliberately stopped before a live attempt.
`truepanel-mission-control.service` must remain active.

The 150-second independent RO guard and 175-second RO-only rescue timer both
start while the USB is read-only and **after the physical button event**,
but before any writable remount. The transfer transport has a per-action
60-second rsync timeout. During RW the exact device and source file are
rechecked. The new file is staged and published with Linux no-replace
semantics. Final backup evidence is committed ONLY after the USB is confirmed
read-only again and both source/destination hash to the exact approved digest.

The last RO-only guardian and timer qualifications do **not** prove real RW
failure restoration; a first live attempt requires a dedicated final go/no-go
review. A degraded RAIDZ1 may become unrecoverable if another disk fails.

## Development qualification, safe to run now

In the BattleStation Git checkout:

```bash
python3 -m unittest discover -s tests -p 'test_loadmaster_tv_nz_supervised_export.py' -v
python3 -m unittest discover -s tests -p 'test_loadmaster_tv_nz_supervised_runner.py' -v
python3 -m unittest discover -s tests -p 'test_supervised_bidirectional_batch.py' -q
python3 -m unittest discover -s tests -p 'test_loadmaster_tv_nz_hdd_export_scope.py' -q
python3 -m tools.loadmaster_tv_nz_supervised_live_fire
findmnt -M /mnt/loadmaster-tv-nz-ro -o SOURCE,FSTYPE,OPTIONS
```

Without live flags, the CLI only hashes/inspects the source and cartridge
and prints `TV_NZ_ONE_FILE_READ_ONLY_READY`. No GPIO/service/mount operation.

## Not yet operator-authorized

The potential physical execution CLI supports three **independent** gates:
`--live-fire`, `--operator-present`, and `--accept-degraded-pool`.
Do NOT use these flags until the new Linux suites pass, the current
watchdog/timer host mechanics are reviewed again, and the operator explicitly
arms the exact one-file transaction. Never start live execution from a
detached terminal or without someone able to press the lower Copy button.

For live runs only, the state directory
`/mnt/SSDs/Applications/Loadmaster-Watchdog-Qualification/tv-nz-production`
must be root-owned `0700`; ensure NAS ACL does not regrant group write.
No private evidence directory is required for safe preview mode.

If anything fails, leave TV N-Z attached and check its mount is `ro`.
Do not stop independent guard/rescue services if USB might still be RW.
Production TruePanel should only be restarted when RO restoration is proven.
