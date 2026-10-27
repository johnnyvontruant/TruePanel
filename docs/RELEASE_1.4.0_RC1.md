# TruePanel 1.4.0-rc1 Release Notes

TruePanel 1.4.0-rc1 is the first candidate for the 1.4 line. It supersedes
1.3.1-rc1 and includes its fixes.

## Highlights

- **Loadmaster.** Labelled USB drives stay mirrored with their NAS folders:
  plug in, press Copy, unplug. Verified, resumable copies; nothing on the NAS
  is deleted (replaced files go to `.loadmaster-replaced`); anything ambiguous
  is held for review instead of guessed. Validated on BattleStation with all
  six media drives.
- **Selftest, tones and drive health.** One command checks the setup; the
  PC speaker announces state changes; every plug-in records SMART health and
  free space, and Mission Control forecasts when a drive will fill.
- **Copy-button-only mode.** Mission Control can review and confirm a plan,
  but only the front-panel button starts a sync.
- **Known deployments.** Staging writes a build stamp with the commit and a
  fingerprint of every file; `verify` reports the deployed commit and warns
  about out-of-band edits. `--stage-only` lists exactly what promotion would
  change and smoke-tests the stage.

## Safety boundaries

- Loadmaster is disabled by default and only touches drives whose label
  matches a configured drive and whose UUID it has adopted.
- Loadmaster never deletes from the NAS. Removals from a drive above the
  configured limit need confirmation; protected folders are never changed.
- Deployments still change only through the guarded upgrade, with a retained
  backup and automatic rollback on failed verification.
- No new storage or hardware-control authority beyond Loadmaster's USB
  mounts and the GPIO75 Copy button read.

## RC1 acceptance gate

Before tagging `v1.4.0-rc1`:

1. GitHub Actions must pass on the exact release-branch commit.
2. Installed-wheel smoke must pass.
3. Both canonical version sources must report `1.4.0rc1`.
4. RC1 must pass guarded BattleStation deployment, with `verify` reporting
   the release commit and "files match".
5. Both TruePanel services must remain active.
6. `python3 -m truepanel.loadmaster selftest` must pass.
7. At least one drive must plug in, plan, sync with the Copy button and
   record its health with a model name.
8. Release evidence must be preserved before tagging.

## AEGIS assurance evidence

Existing 1.3.0 AEGIS assurance envelopes remain unchanged and report
`VersionDrift` against 1.4.0rc1, as they did against 1.3.1rc1. A successor
envelope requires governed requalification and operator review.
