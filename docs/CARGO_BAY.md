# Cargo Bay

Cargo Bay is Mission Control's read-only view of recent Sonarr and Radarr media activity and independent backup evidence.

Its purpose is to answer a practical operator question: **what media has arrived recently, where is it now, what is still moving through the Servarr queue, and which completed items have independent backup evidence?**

Cargo Bay is deliberately observational. It does not start downloads, move or rename media, delete files, alter Servarr state, or perform backups.

## What Cargo Bay observes

Cargo Bay combines several bounded evidence sources:

- recent Sonarr and Radarr `downloadFolderImported` history;
- current Servarr metadata for the corresponding episode or movie file;
- current Servarr queue state for active, pending, or review-worthy downloads;
- filesystem existence and size for the resolved current media path; and
- an optional, independently produced backup manifest.

Historical Servarr file IDs are treated as evidence, not permanent truth. If an imported file has since been renamed or replaced, Cargo Bay attempts to resolve the media object's current file ID and current path before reporting it.

The Mission Control snapshot exposes Cargo Bay as an isolated contract so a failure or unavailable Servarr service does not redefine unrelated TruePanel health state.

## Live download state

Queue records are classified conservatively for display:

- `ACTIVE` for downloads that still have bytes remaining or are actively downloading, queued, or paused;
- `PENDING` for completed downloads that are awaiting import or otherwise appear complete but not yet represented as imported cargo; and
- `REVIEW` for warning, failed, error, or otherwise ambiguous queue states.

Where Servarr provides enough size information, Cargo Bay also derives bounded download progress.

## Backup evidence

Backup state is evidence-backed rather than inferred. Cargo Bay does **not** claim that a file is protected merely because a backup job exists or because a destination is mounted.

The optional backup manifest records observed independent copies by source path, observed size, and observation time. Cargo Bay validates that manifest before using it and correlates the evidence with recent cargo.

The independent producer in `truepanel.cargo.backup_producer` can build this manifest after a separate backup workflow has completed. The producer:

- consumes Cargo Bay's JSON identity for recent media;
- maps configured source prefixes to independent backup prefixes;
- inspects the backup destination without following a final symlink;
- records only observed regular files;
- preserves observed size so mismatches remain visible;
- omits missing copies instead of claiming protection; and
- atomically replaces only the requested manifest output file.

The producer does **not** copy media and does not require the BattleStation source file to be opened or mutated. The backup system remains independent of TruePanel.

## Safety boundary

Cargo Bay and its resolver use read-only Servarr API requests. The backup producer's only write is the explicitly requested manifest/report output. Neither component receives authority to mutate media, Servarr queues, ZFS datasets, snapshots, replication tasks, or backup destinations.

A missing, stale, invalid, mismatched, unmapped, or ambiguous piece of evidence must remain visible as uncertainty. It must not be upgraded into a successful backup claim.

## Operator workflow

A normal workflow is:

1. Sonarr or Radarr imports media.
2. Cargo Bay resolves the imported object to its current media file and displays recent arrival state in Mission Control.
3. A separate backup mechanism copies or replicates the media according to the operator's existing backup policy.
4. The independent Cargo Bay backup producer observes that destination and emits a manifest.
5. Cargo Bay validates and correlates that manifest, allowing Mission Control to show evidence-backed backup state for recent arrivals.

This separation is intentional: **TruePanel observes protection; it does not become the protection mechanism.**

## Development contract

Cargo Bay changes should preserve these invariants:

- Servarr access remains GET-only unless a future feature goes through a separate authority review.
- Historical IDs cannot override current Servarr metadata when current identity can be resolved.
- Path translation must remain explicit and bounded to configured prefixes.
- Backup claims require validated independent evidence.
- Symlink, path-escape, malformed-manifest, and ambiguous-evidence cases fail closed.
- Cargo Bay failure must not contaminate unrelated Mission Control health or reliability state.
- The card must remain usable in Mission Control's phone layout.

See the tests under `tests/test_cargo_*` for the executable contract.