# Loadmaster Mission Control v1: Read-Only Flight Deck

Branch: `feature/loadmaster-mission-control`, based on hardware-qualified
`feature/loadmaster-executor` commit `fc63b62`.

This extends Mission Control's **existing Cargo Bay → Loadmaster drawer**.
It is a telemetry-only integration. It cannot arm the Copy button,
remount a cartridge, run rsync, delete, import, or publish files onto USB.
No new writable HTTP route or control action is introduced.

## Current capabilities

- Display bounded exported, ingested, verified and conflicting item counts.
- Show individual source directions, relative paths, sizes and verdicts.
- Display cartridge identity, last reported mount mode and acceptance receipts.
- Fail closed on missing, stale (>24 h), malformed or insecure report files.
- Always label the status **PREVIEW ONLY**; a report is NEVER authority.
- Does not display an active transfer queue unless the host publishes one.
- Version 1 publisher reports **historical synthetic acceptance evidence**
  only, not general TV library scanning or real-time device discovery.

## Stage-only host qualification

Run these from the *new branch checkout* on BattleStation, not the installed
`/mnt/SSDs/Applications/TruePanel` production checkout.

1. First run the no-write preview, after confirming the spare is still RO:

```sh
cd /mnt/SSDs/Applications/TruePanel-Executor-Stage
python3 -m unittest discover -s tests -p 'test_loadmaster_flightdeck.py' -v
findmnt --mountpoint /mnt/loadmaster-spare-ro -o SOURCE,FSTYPE,OPTIONS
python3 -m tools.loadmaster_flightdeck_publish
```

The preview independently hashes both sides of the completed mixed-direction
acceptance and checks the backup, ingest, consumed-authorization and watchdog
journal evidence. It *does not write anything*.

2. To publish a read-only report, only after the preview passes:

```sh
python3 -m tools.loadmaster_flightdeck_publish --publish-ssd-only
ls -l /mnt/SSDs/Applications/Loadmaster-Watchdog-Qualification/flightdeck-acceptance.json
```

The publisher writes **one private 0600 file to SSD**, atomically. It does
not alter the USB, GPIO, services or live TruePanel config.

3. **Do not modify the production YAML yet.** The optional config key is:

```yaml
mission_control:
  cargo_bay:
    loadmaster:
      flight_deck_snapshot_path: /mnt/SSDs/Applications/Loadmaster-Watchdog-Qualification/flightdeck-acceptance.json
```

This belongs alongside existing Loadmaster settings *only when the operator
authorizes Mission Control deployment*. The snapshot is cached on the existing
Cargo Bay cadence (60 s in the current configuration). This v1 telemetry
expires after 24 h unless republished.

## Validation performed on the Mac development checkout

- 19/19 new stdlib flight-deck tests passed.
- Module compilation and Mission Control embedded JavaScript parsing passed.
- Legacy durable-rsync suite is Linux-only: its temporary-lab safety
  requirements reject macOS's `/var` symlink. Not counted as passes on Mac.
- Previously completed BattleStation executor tests remain the baseline,
  but a fresh on-host regression is required before rollout.

## Safety hold

BattleStation's HDD pool was **DEGRADED** at the last verified check.
This feature does not authorize scanning or transferring production HDD media.
The validated bidirectional physical test was on a disposable spare and SSD
acceptance roots. The installed Mission Control service is intentionally
unchanged by this development branch.
