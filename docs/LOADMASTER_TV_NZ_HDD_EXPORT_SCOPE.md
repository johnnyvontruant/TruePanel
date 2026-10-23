# Checkpoint 20: pinned HDD-to-TV N-Z export scope (read-only)

This staging checkpoint makes the next real-library pilot **narrower**, not
writable. It provides a reviewable, one-file, one-cartridge policy for a future
host-owned physical export runner. It cannot arm GPIO, mount writable or copy.

## Exact pilot
- Cartridge `tv-n-z`, exFAT UUID `6988-53EB`
- Registered USB serial `2532EA8D3DC7`
- Device `/dev/disk/by-id/usb-Micron_CT8000X10SSD9_2532EA8D3DC7-0:0-part2`
- Mounted RO at `/mnt/loadmaster-tv-nz-ro`
- NAS source root `/mnt/HDDs/Shows/TV N-Z`
- Cartridge directory `/mnt/loadmaster-tv-nz-ro/TV N-Z`
- **Only file** `Nobody Wants This (2024)/3x01 - It's Perfect.mkv`
- Exact size **336388391 bytes**
- SHA-256 `c819a0d72cdb18c679824c687559847beb435747bb9f62c252eb906179c554ab`
- Direction **NAS_TO_USB only**

Both cartridge permissions must remain disabled while qualifying. A registry
configuration that silently enables `allow_backup` or `allow_ingest` fails
closed. OS housekeeping files, Daria, foreign paths, changed files, occupied
destinations, symlink chains and swapped USB identities fail closed.

## BattleStation staging tests

```bash
cd /mnt/SSDs/Applications/TruePanel-Executor-Stage
python3 -m unittest discover -s tests -p 'test_loadmaster_tv_nz_hdd_export_scope.py' -v
python3 -m tools.loadmaster_tv_nz_hdd_export_scope
findmnt -M /mnt/loadmaster-tv-nz-ro -o SOURCE,FSTYPE,OPTIONS
```

Read-only qualification computes the source SHA-256 and validates the current
cartridge again. The displayed `plan_digest_preview_only` is NOT an
authorization token. A fresh nonce, durable physical GPIO approval, and
revalidation in a trusted host-owned write runner are still required.

## Required before live transfer
1. Independent verified live guardian must be started in PID 1 mount namespace
   before any RW request and be checked throughout.
2. Independent RO-only rescue **timer must be rearmed for the actual write
   window**. The successful earlier 8-second timer test is not still active.
3. The existing production actuator hard limit to `/mnt/SSDs` is intentional.
   Do not bypass it; introduce a separate narrowly scoped HDD-source guard.
4. GPIO Copy confirmation must be fresh, bound to the exact action/nonce,
   burned durably before entering RW, and used only once.
5. For this pilot **never write to the degraded HDD pool**, delete media or
   replace a destination. Create a new USB file via a no-replace publication.
6. After physically restoring USB to RO, independently hash both source and
   destination and only then commit SSD-hosted evidence.
7. A real writable-mount failure/recovery scenario has **not** been qualified
   on TV N-Z. Any incident of uncertain mount state remains a HOLD.

The degraded RAIDZ1 risk is operator-accepted. No code in this branch changes
the pool or enables unattended media operations.
