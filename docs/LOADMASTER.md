# Loadmaster

Loadmaster moves media between the BattleStation NAS and a set of removable
USB **cartridges** that mirror the NAS library layout. The operator workflow is
meant to be physical and boring:

1. Plug one cartridge into the NAS.
2. Press the front-panel **Copy** button.
3. Wait for the run to finish, then unplug.

New Sonarr/Radarr imports flow onto the cartridge (**backup**, NAS → USB), and
new files added to the cartridge elsewhere flow onto the NAS (**ingest**,
USB → NAS). Nothing is ever deleted on either side.

Loadmaster lives inside TruePanel's Cargo Bay subsystem
(`truepanel/cargo/`, plus the Host Agent controller in `truepanel/host/`).
[Cargo Bay](CARGO_BAY.md) remains the read-only observation layer.

## Cartridges

Each cartridge is one USB drive with the same folder layout as one slice of
the NAS library. The intended set is six drives:

| Cartridge | NAS scope | Role |
| --- | --- | --- |
| Movies #-D | `/mnt/HDDs/Movies/Movies 1-D` | movies |
| Movies E-I | `/mnt/HDDs/Movies/Movies E-I` | movies |
| Movies J-S | `/mnt/HDDs/Movies/Movies J-S` | movies |
| Movies T-Z | `/mnt/HDDs/Movies/Movies T-Z` | movies |
| TV A-M | `/mnt/HDDs/Shows/TV A-M` | tv |
| TV N-Z | `/mnt/HDDs/Shows/TV N-Z` | tv |

Cartridges are declared in a registry file
(`/var/lib/truepanel/loadmaster/cartridges.json`; template in
[examples/loadmaster-cartridges.json](examples/loadmaster-cartridges.json)).
A cartridge is recognized by its **filesystem UUID** and, optionally, its
pinned **USB device serial**. The TV rows and all UUIDs in the example are
placeholders: replace them with the real folder names and the values from
`lsblk -o NAME,UUID,SERIAL,TRAN,FSTYPE` on the NAS.

## How a run works

```
 Sonarr/Radarr imports ──► backlog observer ──► durable backlog (pending-cargo.json)
                                                        │
 plug in cartridge ──► dock: identify + mount read-only │
                              │                         ▼
                              └────────────────► run plan (backup + ingest)
                                                        │ READY
                                                        ▼
                                    Copy button armed for this plan digest
                                                        │ press
                                                        ▼
       re-plan & digest check ──► remount rw ──► verified copies ──► sync + unmount
                                                        │
                       receipt + backup evidence + inventory baseline update
```

### 1. Knowing what needs to move

* **NAS → USB.** The backlog observer (`python3 -m truepanel.cargo.backlog_observer
  --config truepanel.yaml`) reads recent Sonarr/Radarr imports through Cargo
  Bay and appends each new or replaced file to the durable backlog. The backlog
  survives longer than Servarr history, so a cartridge can sit in a drawer for
  weeks. An item leaves the backlog only when verified backup evidence for that
  exact size exists. The observer is a one-shot command and must be scheduled
  (for example a TrueNAS cron job every 15 minutes).
* **USB → NAS.** At plug-in time the cartridge tree is compared with the NAS
  tree and the cartridge's **inventory baseline** (the file list captured at
  commissioning and advanced after every verified run). A cartridge file that
  is absent from both the NAS and the baseline is new and is ingested.

### 2. Plan states

| State | Meaning | Copy button |
| --- | --- | --- |
| `READY` | There is work and nothing is ambiguous. | Armed |
| `CLEAR` | Cartridge already in sync. | Disarmed |
| `HOLD` | Something needs a human (see reason). | Disarmed |

Common HOLD reasons: `NOT_COMMISSIONED` (no inventory baseline),
`IDENTITY_UNVERIFIED` (serial mismatch or unsupported filesystem),
`MULTIPLE_CARTRIDGES` (dock one at a time), `MOUNT_FAILED` (for example the
drive is already mounted elsewhere), and `PLAN_HOLD` with conflicts such as
`DIVERGENT_WITHOUT_BASELINE` or `BOTH_SIDES_CHANGED` (the same path differs on
both sides and Loadmaster will not guess which one wins).

Non-blocking **notices** are reported but never stop a run:

* `RETIRED_ON_NAS` — a cartridge file whose NAS original was removed, renamed,
  or upgraded since the last sync. It stays on the cartridge (no deletes).
* `NAS_NEWER` — the NAS copy changed but is not in the backlog.
* `BACKLOG_SOURCE_GONE` / `BACKLOG_SOURCE_CHANGED` — a backlog row whose file
  vanished or changed size since it was observed; the observer refreshes it.

### 3. The physical press

While a cartridge is `READY`, the Host Agent keeps the Copy-button gate armed
for that exact plan digest, refreshing the plan every `replan_seconds`. The
gate debounces the active-low GPIO75 line and issues at most one confirmation
per digest. Presses while idle, held, clear, or already finished do nothing.

### 3a. Finishing at the NAS or remotely

**At the NAS.** While a cartridge needs attention the front LCD switches to
Loadmaster pages instead of its normal rotation:

| State | LCD shows |
| --- | --- |
| READY | `MOVIES E-I READY` / `Press COPY`, then how much moves each way |
| EXECUTING | percent and progress bar, file *n* of *m*, current file, `Do not unplug` |
| COMPLETE | `MOVIES E-I DONE` / `Safe to remove` (only after the unmount succeeded) |
| HOLD | a short reason (`Not commissioned`, `Conflicts found`, …) |
| UNREGISTERED | `New drive found` and the drive's UUID for the registry |

SELECT (▼) pages through the screens, ENTER (▲) ejects a docked cartridge that
is READY, CLEAR, or on HOLD, and Copy starts a READY transfer. CLEAR shows for
one minute after docking, then the normal rotation resumes.

**Remotely.** The Cargo Bay card in Mission Control has a live **Loadmaster
dock** panel showing the same state, what moves each way, conflicts, copy
progress, and the last result, with three buttons:

* **Start transfer** — asks for confirmation, then starts the exact plan you
  were shown (if the plan changed in the meantime it is refused). Only
  available when `execution.remote_confirmation: true`.
* **Eject** — unmounts the cartridge without transferring.
* **Rescan** — re-plans now. This also re-arms a cartridge that already ran,
  so a drive left plugged in can pick up new imports without a replug.

The virtual LCD in Mission Control mirrors the front panel too, so its ▲/▼
buttons work exactly like standing at the NAS.

Both surfaces read `/run/truepanel/loadmaster-status.json` and send commands
over `/run/truepanel/loadmaster-command.sock`; neither touches hardware
directly.

### 4. Execution

The executor (`truepanel/cargo/executor.py`):

1. Re-plans from live disk state and **refuses to run** unless the fresh plan is
   `READY` with the digest that was confirmed.
2. Checks free space on each destination.
3. Copies each file into a hidden partial file next to its destination
   (named after that exact source version: path, size, mtime), hashing as it
   streams, `fsync`s, stamps the source mtime, drops the page cache and
   **reads the copy back** to compare SHA-256. New files are published with
   Linux `renameat2(RENAME_NOREPLACE)`, so a file that appears at the last
   instant is never overwritten; filesystems that reject the flag fall back to
   a check-then-rename and the receipt records which method was used.
   Planned updates replace atomically.
4. Stops the whole run on device-level errors (no space, I/O error, read-only
   filesystem, device gone); per-file problems fail just that file.
   **Interrupted copies resume.** After an unplug, power loss, or shutdown the
   partial file stays put. The next confirmed run (a new Copy press) reads the
   partial back, proves it is a byte-exact prefix of the unchanged source, and
   continues from there; the finished file is still fully verified. A partial
   that does not match, or belongs to an older version of the source, is
   discarded and the copy starts over.
5. Writes evidence: verified backups are merged into the Cargo backup manifest
   (which clears them from the backlog on the observer's next pass), the
   inventory baseline is advanced, and a receipt is written.
6. Syncs and unmounts the cartridge and reports `safe to remove`.

Every run leaves a JSON receipt in
`/var/lib/truepanel/loadmaster/receipts/<timestamp>-<cartridge>.json` listing
every file, its direction, outcome, and SHA-256. That directory is the
transfer log.

Run results: `COMPLETE`, `PARTIAL` (some files failed; others are safe),
`FAILED` (stopped; reason given), `CANCELLED` (Host Agent shutdown). Any result
requires unplugging and replugging before another run.

## Safety rules

* Delete policy is `never` for every cartridge, enforced by the registry.
* No transfer without a physical press, and no press without a `READY` plan.
* Cartridges are mounted read-only for planning (`nosuid,nodev,noexec`) and
  read-write only for the confirmed run. A cartridge mounted somewhere
  Loadmaster does not own is never touched.
* A registered UUID on a non-USB disk is never treated as a cartridge.
* Symlinks, special files, and paths escaping a root fail closed.
* Servarr access remains read-only. Loadmaster does not tell Sonarr/Radarr to
  rescan after ingest (see open decisions).

## Setup checklist

1. **Registry.** Copy the example to
   `/var/lib/truepanel/loadmaster/cartridges.json`, set real UUIDs (and
   `device_serial` to pin each drive), and real folder names.
2. **Commission each cartridge.** First make the cartridge and NAS scope
   identical (same files, sizes, and mtimes within 2 s). Then capture the
   baseline:

   ```
   python3 -m truepanel.cargo.commission \
     --registry /var/lib/truepanel/loadmaster/cartridges.json \
     --inventory-dir /var/lib/truepanel/loadmaster/inventory \
     --confirm CONFIRM_ZERO_DELTA_BASELINE
   ```

   The command refuses to overwrite an existing inventory.
3. **Backlog.** Initialize once with
   `python3 -m truepanel.cargo.backlog --backlog /var/lib/truepanel/loadmaster/pending-cargo.json --initialize-baseline`,
   then schedule the backlog observer.
4. **Enable.** In `truepanel.yaml` set
   `loadmaster.physical_confirmation.enabled: true` and
   `loadmaster.execution.enabled: true`, then restart the Host Agent.

### Configuration (`mission_control.cargo_bay.loadmaster.execution`)

| Key | Default | Purpose |
| --- | --- | --- |
| `enabled` | `false` | Master switch for plug-in-and-press transfers. |
| `ingest_enabled` | `true` | Allow USB → NAS (each cartridge also has `allow_ingest`). |
| `mount_root` | `/mnt/loadmaster` | Where cartridges are mounted. |
| `inventory_dir` | — | Commissioned baselines, one `<id>.json` per cartridge. |
| `receipts_dir` | — | Run receipts (the transfer log). |
| `verify` | `sha256` | `sha256` read-back verification, or `size` only. |
| `remote_confirmation` | `false` (reference config: `true`) | Allow Start from Mission Control. Eject and Rescan are always available. |
| `ingest_owner` | NAS folder owner | `uid:gid` for ingested files and folders. |
| `poll_seconds` | `3` | Dock scan interval. |
| `replan_seconds` | `20` | Plan/arm refresh interval (must stay below the 30 s confirmation window). |

## Code map

| Module | Role | Writes |
| --- | --- | --- |
| `cargo/cartridges.py` | Registry, path → cartridge assignment | — |
| `cargo/backlog.py`, `cargo/backlog_observer.py` | Durable backlog of NAS → USB work | backlog file |
| `cargo/commission.py` | Zero-delta baseline capture | inventory files |
| `cargo/loadmaster.py` | Tree scanning, sync and backlog planners | — |
| `cargo/run_plan.py` | Combined backup + ingest plan, digest, preflight | — |
| `cargo/dock.py` | USB detection, identity, ro/rw mount, unmount | mounts only |
| `cargo/copy_button.py`, `host/loadmaster_copy_button.py` | GPIO75 debounce/arm/confirm | — |
| `cargo/executor.py` | Verified copies, evidence, receipts | media, manifest, inventory, receipts |
| `host/loadmaster_controller.py` | State machine tying it all together | via the above |

## Progress log

| Milestone | Status |
| --- | --- |
| Cartridge registry, non-actuating planner, Cargo Bay UI (#188) | Done |
| Commissioning baselines (#189) | Done |
| Durable backlog observer, scoped to commissioned roles (#190, #191) | Done |
| SDR Rescue receipt ingestion and filtering (#192–#194) | Done |
| Physical backups scoped to durable backlog (#195) | Done |
| GPIO75 Copy confirmation gate and Host service (#197, #198) | Done |
| USB dock: detection, identity, ro/rw mount lifecycle | Done (this branch) |
| Combined backup + ingest run plan with digest | Done (this branch) |
| Verified executor with receipts, evidence, baseline advance | Done (this branch) |
| Host controller: plug in → arm → press → run → unmount | Done (this branch) |
| Resumable partial copies and `RENAME_NOREPLACE` publish (ideas from the rsync resume lab, checkpoint 3) | Done (this branch) |
| TV cartridges in example registry | Done (placeholders) |
| On-NAS validation of mount/umount, `RENAME_NOREPLACE` and directory fsync on exFAT, using the spare drive | **Next** |
| LCD Loadmaster screens with SELECT paging and ENTER eject | Done (this branch) |
| Mission Control live dock panel with Start / Eject / Rescan | Done (this branch) |
| Unregistered-drive detection (label matches, UUID missing) | Done (this branch) |
| Bay LED / buzzer cues for READY and DONE | Planned |
| Retire backlog rows whose source vanished | Planned |

## Open decisions

* **Servarr after ingest.** Plex is the player and rescans nightly, so
  Radarr not adopting ingested movies is acceptable. Sonarr's own Series
  Refresh runs on a fixed 12-hour schedule that is not adjustable in its
  settings. If Sonarr needs to know about ingested episodes sooner, the option
  is a targeted `RescanSeries` call for just the affected series after a
  run — a narrow Servarr write that needs an explicit decision.
* **Single manifest writer.** The executor merges evidence into
  `backup.manifest_path` under a lock. The standalone backup producer rewrites
  that file wholesale, so it must not target the same path.
* **HOLD resolution.** Conflicts currently need a manual fix (make both sides
  match, or re-commission). A guided resolution flow does not exist yet.
