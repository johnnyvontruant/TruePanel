# Loadmaster physical acceptance and Phase II safety checkpoint

Date: 2026-10-22 (America/Phoenix)
Host: BattleStation, QNAP TVS-671
Development branch: feature/loadmaster-executor
Live-fire implementation commit: be419c1
Physical transaction: one-file, attended, single-use QNAP Copy confirmation

## Grounded acceptance evidence

- Source: /mnt/HDDs/Shows/TV N-Z/VisionQuest (2026)/1x03 - Reboot.mkv
- Destination: /mnt/usb-tv-n-z/TV N-Z/VisionQuest (2026)/1x03 - Reboot.mkv
- Cartridge: tv-n-z, exFAT UUID 6988-53EB, USB serial 2532EA8D3DC7
- Expected and independently verified SHA-256: eb7675e3fa6639376d79995b1cbcd7f864b13ca326674f5bed4118b2f5790f79
- Independently verified destination size: 533754539 bytes
- Physical log: /var/lib/truepanel/loadmaster/live-fire-20261022-attempt4.log
- Result: PHYSICAL_BACKUP_VERIFIED, NEW_VERIFIED_COPY, EVIDENCE_RECORDED, exit 0
- Journal: /var/lib/truepanel/loadmaster/confirmations (single consumed event)
- Manifest: /var/lib/truepanel/loadmaster/backup-manifest.json (historical Collateral entry preserved)
- Postflight: USB remounted read-only; both truepanel.service and truepanel-mission-control.service active
- GPIO characterization: gpio75 active-low, observed down at 12.478s and up at 12.881s; 403ms physical press

## Safety invariant

This acceptance proves exactly one supervised backup, not unattended or batch operation.
The source and preexisting cartridge contents must not be deleted, renamed, or overwritten.
A copy without current physical authorization must fail closed.
A staged feature must not silently alter running production services.

## Phase II release gates

1. Physical confirmation lifecycle, TTL, debounce, one-use evidence tests
2. Read-only diagnostics and durable acceptance evidence
3. Batch *planning* without write authority: bounded set, collision-free, capacity check, stable hashes
4. Controlled batch execution only after separate explicit acceptance and per-file verification
5. Mission Control status visibility only after safe read-only status API and UI validation
6. Simulated crash, partial publish, mismatched hashes, replay and power-loss recovery coverage
7. Full regression and supervised hardware acceptance before production rollout

## Explicit exclusions

No automatic USB writes, no unattended button simulation, no existing USB file replacement,
no automatic movement of media, no deletion of source or cartridge content, no production
deployment of experimental host ownership changes, no bulk transfer authorization.

This checkpoint intentionally does not assert Phase II batch execution or Mission Control UI is complete.
