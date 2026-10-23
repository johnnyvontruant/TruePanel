# Checkpoint 24: Production Loadmaster queue and Flight Deck evidence

**Status: staging-only, read-only.** Based on the **verified** single-file
physical copy of *Nobody Wants This* S03E01 on the actual TV N-Z cartridge.
This branch does not change a TrueNAS service, Mission Control config, GPIO
owner, mounted cartridge, durable backlog or the source library.

## Components

- `truepanel/cargo/queue_preview.py`: pure, bounded ledger-only view grouped
  by registered cartridges. Most-specific cartridge prefix wins. No source
  file stat/hash, USB mount, network API or path traversal. Output never grants
  physical authorization. Includes aggregate counts for unmapped paths and
  excluded Daria, OS housekeeping and unsupported three-plus-level paths.
  Queue rows are always `REVIEW`, even when registry flags permit backup;
  `BACKUP_DISABLED` remains visible on disabled cartridges.
- `tools/loadmaster_queue_preview.py`: CLI to inspect existing registry and
  backlog. No mount or media access.
- `tools/loadmaster_tv_nz_production_flightdeck.py`: independently rehashes
  exactly one known source and its published USB destination, requires a
  matching SSD-hosted backup manifest, checks the pinned TV N-Z UUID/serial and
  RO mount both before and after hashing, and constructs the **existing**
  `truepanel.loadmaster.flightdeck.v1` format. Reports guard `UNKNOWN`:
  present RO state is not proof of a specific watchdog incident.
  The default is output-only; `--publish-ssd-only` atomically updates one
  0600 report on SSD, not a USB file.
- `tests/test_loadmaster_production_interrupt_lab.py`: disposable /tmp tests
  for interrupted outgoing and incoming rsync, no published partial, mandatory
  fresh transfer approval after interruption, matching SHA-256 on a completed
  reattempt, and refusal to overwrite conflicting destination bytes.

## First BattleStation qualification (no media writes)

Use a clean staging checkout of this branch:

```bash
python3 -m unittest discover -s tests -p 'test_loadmaster_queue_preview.py' -v
python3 -m unittest discover -s tests -p 'test_loadmaster_production_flightdeck.py' -v
python3 -m unittest discover -s tests -p 'test_loadmaster_production_interrupt_lab.py' -v
python3 -m unittest discover -s tests -p 'test_loadmaster_tv_nz_supervised_export.py' -q
python3 -m tools.loadmaster_queue_preview --cartridge-id tv-n-z --max-rows 5
python3 -m tools.loadmaster_tv_nz_production_flightdeck
python3 -m tools.loadmaster_tv_nz_ro_guard --preflight
```

These test /tmp rsync simulations use synthetic 8 MiB payloads and real
interruptions but **never target production**. The queue command uses only
the ledger and registry. The flightdeck command hashes just the original
verified pilot episode and the new USB copy.

If all pass, a separately attended command may publish **SSD telemetry only**:

```bash
python3 -m tools.loadmaster_tv_nz_production_flightdeck --publish-ssd-only
```

The output is fixed at
`/mnt/SSDs/Applications/Loadmaster-Watchdog-Qualification/flightdeck-tv-nz-production.json`.
This file remains strictly `PREVIEW_ONLY`. To actually show in Mission
Control requires a separate, reviewed config/deployment step specifying
`mission_control.cargo_bay.loadmaster.flight_deck_snapshot_path`. Do not
edit production YAML or restart Mission Control as part of this checkpoint.

## Deliberate holds

- Do not re-run the single-file TV N-Z physical execution: the destination
  now exists, and safe no-overwrite mode must reject it.
- The new queue rows are **unverified backlog observations**. An item in
  the backlog may also have a completed pilot receipt in the separate
  private production manifest; no queue item is silently cleared.
- Real cartridge multi-file execution, changed-source recovery, USB->HDD
  ingest, Daria handling, automated button arbitration, and scheduled
  repetitive copying are **not authorized**.
- A real writable-mount crash has still not been deliberately induced on
  TV N-Z. Lab rsync interruption alone is not a substitute for proving
  physical watchdog/rescue recovery under fault.
- HDD RAIDZ1 is degraded; the prior user-approved single-file copy does
  not imply permission to perform an unattended bulk transfer.
- The current registry remains `allow_backup: false`,
  `allow_ingest: false` for TV N-Z. Keep both disabled.

Checkpoint 25 will reconcile verified production manifests into a unified
read-only backlog view without deleting source entries and review the GPIO /
mount-ownership handoff for bounded 2-to-3-file attended sessions.
