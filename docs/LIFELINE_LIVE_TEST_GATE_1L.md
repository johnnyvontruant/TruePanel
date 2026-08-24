# Project Lifeline Live Certification: Gate 1L

Date: 2026-08-23 America/Phoenix

Certified source head before documentation-only commit:

`57195a5432ffd2217f0fae00d11dc46715331ca3`

## Purpose

Gate 1L rehearses the installed TruePanel/Mission Control runtime from a disposable installation tree while preserving a strict no-production-mutation boundary.

The gate verifies that the managed install file shape, configuration preservation, Mission Control systemd unit, Lifeline persistent-state contract, HTTP server, browser assets, and healthy-drive fingerprint capture work from an installed-tree layout rather than a source checkout.

## Initial Gate 1L HOLD

The first attempt passed all checks through:

- certified source guard
- real ONLINE pool baseline
- production configuration/service/unit guards
- disposable install-tree copy
- managed-file presence/exclusion checks
- exact production configuration copy into the rehearsal tree
- runtime dependency import check
- installed-tree compilation
- installed-tree import isolation
- installed CLI startup

It then stopped before service rendering because `/tmp` on BattleStation is mounted `noexec`, so directly executing `/tmp/.../start-truepanel.sh` returned permission denied.

No production service, systemd unit, `/var/lib` state, hardware, or storage state changed.

Disposition: harness/environment HOLD only. The corrected rerun invokes copied lifecycle scripts through `bash` and preserves the host's `noexec` policy.

## Gate 1L-R PASS

Gate 1L-R resumed from the failed boundary and passed.

### Rehearsal environment

- disposable installed tree: `/tmp/truepanel-lifeline-gate1l/install`
- `/tmp` confirmed `rw,nosuid,nodev,noexec`
- copied `start-truepanel.sh` SHA matched certified source exactly
- lifecycle script invoked through `bash`
- real systemd writes: none
- real `/var/lib` writes: none
- production service restarts: none
- hardware actions: trapped/forbidden
- storage mutations: none

### Installed-tree systemd contract

The disposable startup path rendered a Mission Control service with:

- `WorkingDirectory` bound to the disposable install tree
- `StateDirectory=truepanel/lifeline`
- `StateDirectoryMode=0700`
- existing Mission Control hardening retained

`systemd-analyze verify` accepted the rendered unit.

### Installed-tree runtime and HTTP stack

The Python runtime imported `truepanel` from the disposable installed tree, not the production tree or source checkout.

The rehearsal then started an actual `MissionControlServer` on an ephemeral localhost port and verified:

- `/api/v1/status` returned HTTP 200 with Lifeline status
- dashboard HTML injected the Lifeline markers/assets
- `/lifeline.js` returned HTTP 200
- `/lifeline-actions.js` returned HTTP 200
- browser-supplied `bay` in Identify request returned HTTP 422 before hardware dispatch
- nonexistent session returned HTTP 404 before hardware dispatch
- configuration writes remained disabled
- hardware identify trap recorded zero calls

### Healthy fingerprint evidence

The installed-tree `DriveFingerprintProvider` performed live read-only fingerprint capture.

Bay 3 again resolved to the already-certified member identity and exact media properties. The public Lifeline fingerprint summary reported four verified/non-conflicted records without exposing serial/WWN payloads.

Private rehearsal state verified:

- Lifeline state directory mode `0700`
- fingerprint ledger mode `0600`
- no repair session created while the pool was healthy

### Final guards

After the HTTP server shut down:

- real `/var/lib/truepanel/lifeline` remained absent
- real `/var/lib/truepanel` metadata remained unchanged
- real `/var/lib/truepanel` contents remained unchanged
- production `truepanel.yaml` hash remained unchanged
- production LCD service PID remained unchanged
- production Mission Control PID remained unchanged
- production Mission Control unit hash remained unchanged
- `HDDs` remained ONLINE
- all six RAIDZ1 members remained ONLINE
- no known data errors were reported

## Result

**PASS: Gate 1L-R**

The isolated installed-tree rehearsal demonstrated that Project Lifeline's installed runtime, persistent-state shape, Mission Control HTTP surface, browser assets, healthy-drive fingerprint collection, and mutation guards function from a disposable installation without altering production.

No production deployment, service restart, hardware action, ZFS/storage mutation, or storage-write authority was granted.

## Next boundary

The next bounded step is a production-promotion rehearsal only: model and verify the exact backup, stage, verification, restart, health-check, and rollback choreography against disposable paths and captured production metadata before any actual production-tree promotion is authorized.
