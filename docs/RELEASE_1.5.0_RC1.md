# TruePanel 1.5.0-rc1 Release Notes

TruePanel 1.5.0-rc1 is the first candidate for the 1.5 line. It builds on
1.4.0 stable and includes every change merged to `main` since.

## Highlights

- **Friendly fault view.** A fault now opens with one plain headline and
  three cards: what is wrong, what it affects, and what is protecting you.
  A drive-bay picture marks the failed bay, and an eight-step guide walks
  through a replacement using the TrueNAS Replacing Disks procedure and the
  QNAP TVS-x71 hardware manual. TruePanel ticks the steps it can see for
  itself: backup acknowledged, replacement detected, resilver running, pool
  online. When nothing is wrong the same spot shows an all-clear summary.
- **Pilot and Flight Engineer.** Pilot shows a compact card with only your
  next step; Flight Engineer shows the full guide. The card folds to one line
  for a known fault you are waiting to fix, and the Storage status light
  jumps straight to it.
- **Named even when silent.** A failed drive that has stopped responding is
  named from the active Lifeline session and the bay mirror (bay, model,
  serial suffix) instead of "unknown".
- **Technical details drawer.** System Health, Flight Director, AEGIS /
  Checkride, Watchtower and the advisory banner sit in one drawer under the
  fault view. They are moved, not removed, and keep updating.
- **Flight Recorder.** New alerts, buzzer activations and Loadmaster tone
  requests are written to `/var/lib/truepanel/logs/flight.log`, readable with
  `python -m truepanel.flight_logs` or the Flight Logs overlay.
- **Fixes.** Loadmaster's activity log no longer drops Sonarr/Radarr history
  in large bursts; the hottest-drive card no longer borrows an incident's
  bay; the fan runtime tolerates a Fintek controller that appears late at
  boot.

## Safety boundaries

- The fault view changes nothing on the NAS by itself. Its only actions are
  the existing guarded Lifeline backup-state acknowledgement and bay identify
  LED, with their existing intent headers and confirmation phrases, offered
  only when TruePanel already permits them.
- Steps ticked in the browser are stored in that browser only and never clear
  a Checkride, Lifeline or Pathfinder gate.
- The Flight Recorder and Flight Logs API are read-only and fail-open; a
  logging failure never blocks an alert or hardware action.
- No new storage, fan, LCD or configuration authority.

## RC1 acceptance gate

Before tagging `v1.5.0-rc1`:

1. GitHub Actions must pass on the exact release-branch commit.
2. Installed-wheel smoke must pass.
3. Both canonical version sources must report `1.5.0rc1`.
4. RC1 must pass guarded BattleStation deployment, with `verify` reporting
   the release commit and "files match".
5. Both TruePanel services must remain active.
6. With the Bay 3 fault active, Mission Control must show the fault view
   directly under the virtual front panel, name Bay 3 with its model and
   serial suffix, show the compact card in Pilot and the full guide with
   Technical details in Flight Engineer.
7. `python -m truepanel.flight_logs` must read entries written after the
   deployment.
8. Release evidence must be preserved before tagging.

Promotion to 1.5.0 follows `docs/RELEASE.md` after a quiet observation
period on BattleStation.

## AEGIS assurance evidence

Existing 1.3.0 AEGIS assurance envelopes remain unchanged and report
`VersionDrift` against 1.5.0rc1, as they did against 1.4.0. A successor
envelope requires governed requalification and operator review.
