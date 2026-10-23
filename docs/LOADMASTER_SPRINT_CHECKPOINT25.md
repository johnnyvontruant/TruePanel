# Loadmaster Checkpoint 25: Consolidated Sprint Finish

This milestone replaces the former one-checkpoint-at-a-time workflow with
**one attended operator command**. It does not authorize another physical
copy. The previous 336388391-byte TV N-Z pilot is the only real verified file.

## One-shot operator sequence

On BattleStation, in a clean TruePanel Executor Stage checkout:

```bash
git fetch origin feature/loadmaster-production-receipt-reconcile
git switch -c feature/loadmaster-production-receipt-reconcile FETCH_HEAD
python3 -m tools.loadmaster_sprint_finish --activate-ui
```

If the branch exists already, switch to it and fast-forward to FETCH_HEAD,
rather than creating a duplicate. All three operations should run inside a
temporary Bash subshell so `set -e` cannot close the operator's SSH shell.

The command:
1. Runs **eight bounded Linux regression suites**, including new receipt
   reconciliation and Mission Control configuration safety checks; the
   already-qualified interrupted-rsync lab uses disposable /tmp media only.
2. Verifies TruePanel and Mission Control production services are active.
3. Pins the actual TV N-Z device read-only, reads the existing registry and
   backlog **without changing either**, groups and filters queue entries.
4. Rehashes the actual production backup source and USB copy and validates
   the root-private backup receipt.
5. Compares receipt timestamp and file size against the ledger's required_after
   to print `VERIFIED_ELIGIBLE`, `STALE_RECEIPT_HOLD`,
   `SIZE_MISMATCH_HOLD` or `NOT_CURRENTLY_QUEUED`.
6. Atomically publishes a **0600 SSD-only** snapshot accepted by the existing
   read-only Mission Control Flight Deck provider.
7. With `--activate-ui`, verifies installed provider supports that setting,
   checks the TruePanel application's existing YAML schema, creates a private
   backup, inserts only the exact new `flight_deck_snapshot_path` line, and
   restarts **Mission Control only**. On failure the original YAML is restored
   and restart retried. If installed code lacks the setting, it refuses edits.

## Explicitly unchanged

- TV N-Z cartridge mounted read-only throughout.
- No HDD writes, USB writes, rsync or Copy-button GPIO action.
- The 33 existing pending-cargo ledger rows are **not pruned or mutated**.
- No changes to the cartridge registry's disabled physical policies.
- No automatic broad backup or USB->NAS ingest, including protected Daria.
- This UI snapshot is **current evidence**, not transfer authority. Existing
  reader deliberately marks telemetry older than 24h as stale; a recurrent
  production source renewal needs a later change.

## Return conditions

- All eight regressions pass on BattleStation (not only mocked on Mac).
- Queue shows the exact registered TV N-Z queue totals.
- Current source and USB copy SHA-256 agree with the receipt.
- UI activation says `LOADMASTER_UI_CONNECTED` or already connected.
- Both production services remain active and USB remains RO.
- No media content or durable pending state changed.

## Backup and rollback

A timestamped root-private copy of the original TruePanel YAML is left under
`/mnt/SSDs/Applications/Loadmaster-Watchdog-Qualification/tv-nz-production/`
if the activation changed configuration. Rollback is automatic when the
Mission Control restart fails its service-active checks. On any hold,
report the diagnostic instead of forcing an edit/restart.

## Remaining production expansion

The single-file runner correctly **rejects the pilot destination on repeat**.
To copy more than one pending episode per physical confirmation, the future
batch runner needs its own bounded immutable source hashes, post-copy receipts,
freshly consumed GPIO authorization, verified both-side mounts and independence
of watchdog/timer. Do not increase the number of files in the existing
single-file runner or lift the intentional `/mnt/SSDs` acceptance limit
in the spare batch actuator. The degraded HDD RAIDZ1 still requires caution.
