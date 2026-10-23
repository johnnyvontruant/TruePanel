# Loadmaster: macOS / Windows housekeeping exclusions

This change adds a **conservative, case-insensitive name policy** used by
Loadmaster's recursive NAS/USB planner, bidirectional discovery, backlog
planner, inventory export, and the physically approved bidirectional executor.

## Excluded

| Source | File examples | Directory examples |
| --- | --- | --- |
| macOS | `.DS_Store`, `._*` AppleDouble companions, `.localized`, `.apdisk`, `.VolumeIcon.icns` | `.Spotlight-V100`, `.Trashes`, `.fseventsd`, `.TemporaryItems`, `.DocumentRevisions-V100`, `.AppleDouble`, `__MACOSX` |
| Windows | `desktop.ini`, `Thumbs.db`, `ehthumbs.db`, `thumbcache_*.db`, `iconcache_*.db` | `System Volume Information`, `$RECYCLE.BIN`, `RECYCLER`, `Recycled` |
| Loadmaster internal | | `.loadmaster-rsync-stage` |

Matching is by exact name or narrow cache prefix/suffix patterns, anywhere
under the media scope, ignoring case. Entire known housekeeping directories
are excluded from traversal.

**Not excluded:** all files beginning with a dot; all Windows files marked
"hidden" or "system"; unknown files; legitimate video, subtitle, artwork,
and `.nfo` assets. This avoids silently throwing out actual media files.

This policy only affects **planning** and **approval**, never the source
contents: excluded files are neither copied nor removed. Metadata appearing
in previously persisted inventories also does not create a "missing on
one side" action. A manually supplied physical plan targeting housekeeping
is rejected before any transfer is attempted.

The hardware owner, independent RO watchdog, physical Copy-button approval,
no-overwrite and no-delete restrictions all remain unchanged.

## No-hardware tests

```sh
cd /mnt/SSDs/Applications/TruePanel-Executor-Stage
python3 -m unittest discover -s tests -p 'test_loadmaster_os_housekeeping.py' -v
python3 -m unittest discover -s tests -p 'test_loadmaster_bidirectional_host_scope.py' -q
python3 -m unittest discover -s tests -p 'test_loadmaster_bidirectional_cargo.py' -q
python3 -m unittest discover -s tests -p 'test_supervised_bidirectional_batch.py' -q
python3 -m unittest discover -s tests -p 'test_loadmaster_checkpoint11_runner.py' -q
```

Only run in the development checkout on BattleStation. No USB remount,
Copy-button press or live transfer is required for these tests.

The production TV library stays gated until the degraded HDD RAIDZ1 has
restored redundancy and an explicit deployment review is complete.
