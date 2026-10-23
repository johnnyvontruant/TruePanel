# Loadmaster

Loadmaster keeps six USB drives and their matching NAS media folders in sync.

1. Plug a drive into the NAS.
2. Press **Copy** on the front panel, or **Start sync** in Mission Control.
3. Unplug when it says **Safe to remove**.

New Sonarr/Radarr downloads go to the drive, files you added to the drive
elsewhere (for example upgrades from your laptop) come to the NAS, and the
drive is kept as a mirror of the NAS.

The code is the self-contained `truepanel/loadmaster/` package. It replaces
the earlier Cargo Bay Loadmaster work (`truepanel/cargo/loadmaster*`,
`backlog*`, `commission.py`, `copy_button.py`), which is left in place for
now and is not used by it.

## Drives

| Drive (filesystem label) | NAS folder |
| --- | --- |
| Movies 1-D | `/mnt/HDDs/Movies/Movies 1-D` |
| Movies E-I | `/mnt/HDDs/Movies/Movies E-I` |
| Movies J-S | `/mnt/HDDs/Movies/Movies J-S` |
| Movies T-Z | `/mnt/HDDs/Movies/Movies T-Z` |
| TV A-M | `/mnt/HDDs/Shows/TV A-M` |
| TV N-Z | `/mnt/HDDs/Shows/TV N-Z` |

A USB filesystem whose **label** matches a drive name (case-insensitive) is
that drive. On the drive, files are expected inside a folder with the same
name (`TV A-M/...`); set `usb_folder: ""` for a drive whose files sit at the
top level.

The first time a drive is seen, Loadmaster remembers its filesystem UUID. If a
different physical drive later shows up with the same label, Loadmaster stops
with **NEW_DRIVE** and nothing happens until you press **Adopt this drive** in
Mission Control. Adopting treats it as a first sync.

## How Loadmaster decides what to do

For every file it compares three things: what is on the NAS, what is on the
drive, and what both held at the end of the **last sync** (the drive record in
`state_dir/drives/`). The record is what lets it tell "you deleted this on the
NAS" from "this is new on the drive". There is no setup or commissioning step;
the first sync creates it.

| Situation | Action |
| --- | --- |
| New or changed on the NAS (Sonarr/Radarr import) | Copy to the drive |
| New on the drive | Copy to the NAS |
| Removed from the NAS since the last sync (for example a Radarr upgrade deleted the old file) | Remove from the drive — the drive mirrors the NAS |
| Changed on the drive since the last sync, unchanged on the NAS | Copy to the NAS |
| Changed on both sides, or different with no record | The **newest** file wins |
| Same modification time but different size | Conflict: nothing happens until resolved |
| Video removed from the drive and a new video added for the same episode (`S01E05`), or in the same folder when names have no episode number (movies) | Upgraded on the laptop: the new file comes to the NAS and the old NAS file is retired (moved, not deleted) |
| Removed from the drive for any other reason | Copied back to the drive |
| First sync of a drive | Copy whatever each side lacks. **Nothing is ever removed on a first sync.** |

Files whose names start with `.`, and `$RECYCLE.BIN`, `System Volume
Information`, `Thumbs.db`, `desktop.ini` and `lost+found`, are ignored on both
sides. Sonarr, Radarr and Plex ignore them too. Names that exFAT/NTFS cannot
store (`< > : " | ? * \`) are skipped and listed rather than failing the sync.

## Safety rules

* **The NAS never loses data.** When Loadmaster has to replace or retire a NAS
  file, the old version is moved to `.loadmaster-replaced/<date-time>/` inside
  that drive's NAS folder. It is hidden, so Plex, Sonarr and Radarr normally
  skip it. Clear it out yourself when you're happy.
* **Nothing moves without a decision.** Either the Copy button is pressed or
  you confirm **Start sync** in Mission Control. Mission Control shows the exact
  list first.
* **No surprises between preview and copy.** Right before copying, Loadmaster
  re-checks both sides. If anything changed since the plan was shown, it stops
  and shows the new plan.
* **Large removals need confirmation in Mission Control.** More than
  `large_delete_files` (default 100) removals puts the drive in **CONFIRM**.
  The Copy button alone will not start it.
* **An empty NAS folder stops everything.** If a NAS folder that previously
  had files is suddenly empty (an unmounted dataset, for example), Loadmaster
  holds instead of mirroring that to the drive.
* **Every copy is verified.** Files are written to a hidden partial file, read
  back from the disk and compared by SHA-256, and only then put in place. New
  files are put in place with an atomic "no replace" rename, so a file that
  appears at the last moment is never overwritten.
* **Interrupted copies resume.** If the drive is unplugged or power is lost
  mid-copy, the partial file stays. The next sync proves it matches the source
  byte for byte and continues from there.
* **Old NAS files are retired only after the replacement arrives.** If any copy
  in a sync fails, retirements in that sync are skipped.
* **Only one drive at a time**, and only over USB. A drive already mounted
  somewhere else is left alone.
* Drives are mounted read-only while being checked, and read-write only while
  copying. They are synced and unmounted when the sync finishes.
* Mission Control has no login, like the rest of the dashboard: anyone who can
  open it on your network can start a sync. Set `remote_start: false` to allow
  starting only from the Copy button.

## At the NAS: front panel

While a drive needs attention, the LCD shows Loadmaster screens instead of its
normal rotation:

| State | LCD |
| --- | --- |
| CHECKING | `TV A-M` / `Checking...` |
| READY | `TV A-M READY` / `Press COPY`, then counts each way and removals |
| CONFIRM | `Confirm in TP` and how many files would be removed |
| COPYING | percent with a progress bar, file *n/m*, current file, `Do not unplug` |
| DONE | `TV A-M DONE` / `Safe to remove`, then what was copied |
| HOLD / NEW_DRIVE | the reason, wrapped over two screens |
| CLEAR | `Up to date` (for one minute) |

* **SELECT (▼)** steps through the screens.
* **ENTER (▲)** ejects the drive (unmounts without syncing).
* **Copy** starts a READY sync.

When no drive is plugged in, the normal rotation includes a Loadmaster page
showing which drive to plug in next and how much is waiting for it.

## Remotely: Mission Control

The **Loadmaster** card shows:

* the plugged-in drive, its state and the exact list of changes;
* **Start sync**, **Stop**, **Eject**, **Rescan** and **Adopt this drive**;
* every drive with when it was last synced and how much is waiting for it,
  worked out from the NAS even while the drive is in a drawer;
* recent activity: Sonarr/Radarr imports and deletions, and each sync.

**Stop** finishes the current block and stops; finished files are kept and the
unfinished file resumes next time. **Rescan** re-checks a drive that is still
plugged in, for example after new downloads arrive.

## Sonarr and Radarr

Loadmaster reads Sonarr and Radarr history every five minutes, using the same
read-only connection settings as Cargo Bay, and records imports, upgrades,
renames and deletions in the activity log with the drive each belongs to. The
log is for you. Sync decisions come from comparing the folders directly, so a
download Sonarr missed, or a file you added by hand, is still picked up.

Ingested files reach Plex on its nightly scan. Sonarr refreshes series on its
own schedule (every 12 hours, not adjustable in its settings).

## Setup

1. **Label the drives** with exactly the names above. If they are already
   labelled, `lsblk -o PATH,LABEL,UUID,FSTYPE,TRAN` on the NAS shows them.
2. **Check the paths** in the `loadmaster:` section of `truepanel.yaml`.
3. **Try a dry run** on one drive before enabling anything. Mount it by hand
   (read-only) and run:

   ```
   sudo mount -o ro /dev/sdX1 /mnt/test
   python3 -m truepanel.loadmaster --config truepanel.yaml preview "TV A-M" "/mnt/test/TV A-M"
   sudo umount /mnt/test
   ```

   This lists exactly what a first sync would do and changes nothing. It works
   while Loadmaster is still disabled.
4. **Enable**: set `loadmaster.enabled: true` and restart TruePanel. The
   service runs inside the TruePanel LCD process. To run it on its own instead
   (for testing), use `python3 -m truepanel.loadmaster run`.

### Settings (`loadmaster:`)

| Key | Default | Meaning |
| --- | --- | --- |
| `enabled` | `false` | Turn Loadmaster on. |
| `drives` | — | `name`, `nas_path`, optional `usb_folder`. |
| `state_dir` | `/var/lib/truepanel/loadmaster` | Drive records, activity log, receipts. |
| `mount_root` | `/mnt/loadmaster` | Where drives are mounted. |
| `remote_start` | `true` | Allow Start sync from Mission Control. |
| `copy_button` | `true` | Use the front-panel Copy button. |
| `verify` | `sha256` | `sha256` reads every copy back; `size` only checks the size. |
| `large_delete_files` | `100` | Above this many removals, confirm in Mission Control. |
| `ingest_owner` | NAS folder owner | `uid:gid` for files and folders brought to the NAS. |

### Files Loadmaster keeps

| Path | What |
| --- | --- |
| `state_dir/drives/<drive>.json` | The last-sync record for each drive. |
| `state_dir/activity.jsonl` | Activity log (rotates at 5 MB). |
| `state_dir/receipts/` | One JSON receipt per sync, listing every file and its SHA-256 (last 100 kept). |
| `/run/truepanel/loadmaster-status.json` | Live status read by the LCD and Mission Control. |
| `/run/truepanel/loadmaster-command.sock` | Commands from the LCD and Mission Control. |

## Code map

| Module | Job |
| --- | --- |
| `config.py` | Settings and the drive list. |
| `scan.py` | Walks a folder; size and mtime per file. |
| `state.py` | Drive records, activity log. |
| `plan.py` | The decision table above; pure and fully tested. |
| `transfer.py` | Verified, resumable copy; checked delete; retire to `.loadmaster-replaced`. |
| `run.py` | Carries out a plan in a safe order and updates the drive record. |
| `dock.py` | Finds drives by label over USB; mounts and unmounts. |
| `servarr.py` | Sonarr/Radarr history to the activity log. |
| `service.py` | The state machine, Copy button, worker threads. |
| `link.py` | Status file and command socket. |
| `lcd.py` | Front-panel screens. |
| `__main__.py` | `run`, `status`, `preview`. |

Tests: `tests/test_lm_*.py`.

## Not yet verified on the NAS

The package is tested against real files in temporary folders and in a browser,
but not yet on the NAS itself. Before relying on it, check with the spare drive:

* mounting and unmounting the drive's filesystem (exFAT or NTFS) on TrueNAS;
* the atomic "no replace" rename on that filesystem (the receipt records which
  method was used);
* that the Copy button reads correctly from the LCD process;
* that the drive's folder layout matches `usb_folder`.
