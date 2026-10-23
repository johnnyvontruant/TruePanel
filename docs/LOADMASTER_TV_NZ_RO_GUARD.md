# Loadmaster TV N-Z: independent read-only watchdog qualification

## Pinned physical identity

This guardian is separate from the disposable spare guardian.

- TV N-Z serial: `2532EA8D3DC7`
- exFAT UUID: `6988-53EB`
- by-id: `/dev/disk/by-id/usb-Micron_CT8000X10SSD9_2532EA8D3DC7-0:0-part2`
- mount: `/mnt/loadmaster-tv-nz-ro`
- the proposed HDD backup source remains
  `/mnt/HDDs/Shows/TV N-Z/Nobody Wants This (2024)/3x01 - It's Perfect.mkv`
- its preflight SHA-256 is
  `c819a0d72cdb18c679824c687559847beb435747bb9f62c252eb906179c554ab`

This code CANNOT initiate a USB writable remount, read/write episode
content, or accept a GPIO button press. Recovery logic can only attempt
to return the exact authenticated cartridge from RW to RO.

The RO-only host test starts a short independent systemd guardian in
PID 1's host mount namespace with a synthetic sleep process as owner.
It checks a fresh owner/guardian/plan-bound status, terminates only that
synthetic sleep, verifies `RESTORED_RO`, validates service success,
and independently attests that TV N-Z stayed RO.

**No production transfer** is implemented in this checkpoint. In particular,
the existing bidirectional actuator remains intentionally scoped to
`/mnt/SSDs`; do not modify or bypass that restriction.

## BattleStation qualification in development checkout

Run ONLY when TV N-Z is still mounted RO at the pinned mountpoint:

```sh
cd /mnt/SSDs/Applications/TruePanel-Executor-Stage
python3 -m unittest discover -s tests -p 'test_loadmaster_tv_nz_ro_guard.py' -v
python3 -m tools.loadmaster_tv_nz_ro_guard --preflight
python3 -m tools.loadmaster_tv_nz_ro_qualification
findmnt -M /mnt/loadmaster-tv-nz-ro -o SOURCE,FSTYPE,OPTIONS
```

If those pass, the separate attended host-namespace read-only test:

```sh
python3 -m tools.loadmaster_tv_nz_ro_qualification --ro-test
findmnt -M /mnt/loadmaster-tv-nz-ro -o SOURCE,FSTYPE,OPTIONS
```

This last command starts a *transient* systemd unit and writes private
status to `/mnt/SSDs/Applications/Loadmaster-Watchdog-Qualification/tv-nz-ro-qualification`.
It does not remount RW. A guardian that is still active should not be
forcibly stopped: its synthetic owner exiting triggers RO recovery.

Only proceed if the output includes
`TV_NZ_HOST_NAMESPACE_RO_GUARD_QUALIFIED` and `mount_mode: ro`.

## Remaining work before actual production copy

1. Qualify a separate timed independent RO rescue using this exact pin.
2. Build an explicit HDD-source, NAS-to-USB-only supervised executor with
   true host GPIO authorization and no-overwrite commit semantics.
3. Reattest current cartridge identity, read-only state, source checksum,
   and destination absence immediately before each physical operation.
4. Persist backup evidence only after the USB is back RO and the final
   destination hashes to the approved source.
5. No USB-to-HDD ingestion in this pilot. The degraded HDD RAIDZ1 risk
   has been accepted, but exact file scope and physical confirmation remain
   mandatory. Daria restoration is permanently excluded.
