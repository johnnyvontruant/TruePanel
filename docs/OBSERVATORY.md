# Project OBSERVATORY

Project OBSERVATORY gives TruePanel a normalized, read-only answer to a new
question: **what is this machine doing right now?**

OBSERVATORY is a TruePanel 1.4 experiment. It adds activity evidence without
adding storage, fan, LCD, LED, application, or other control authority.

## Data flow

```text
existing TruePanel status evidence ─┐
                                    ├─ activity providers ─ registry ─ Mission Control projection
optional external read-only source ─┘                         │
                                                              └─ CURRENT ACTIVITY
```

The activity model is versioned and presentation-neutral. Providers emit
normalized observations with source, kind, state, confidence, intensity,
progress, optional timing/context, and evidence labels. The registry isolates
provider failures, rejects duplicate source names, orders output
deterministically, and bounds the combined observation count.

Mission Control applies a second presentation/privacy boundary before activity
is placed in `/api/v1/status`.

## Providers

### ZFS

ZFS activity is always derived from the storage evidence already present in the
TruePanel status snapshot. OBSERVATORY does **not** run another `zpool` command.

Current normalized operations:

- scrub: moderate maintenance activity
- resilver: high recovery activity

When scrub and resilver evidence are simultaneously active, shared progress is
not attributed to either operation. Progress remains unknown rather than being
guessed.

### Plex

Plex is optional and disabled when it is not configured. The provider performs
only a read of Plex `/status/sessions` and carries no Plex control authority.

The provider may normalize rich session data internally, but Mission Control
redacts media identity before serialization. The cockpit receives generic
workload descriptions such as `Plex playback`, not media titles, user names,
player names, server URLs, or credentials.

Provider/network/parser failures collapse to `unavailable` without exposing raw
exception text.

## Secure Plex configuration

Do not put a Plex token directly in `/etc/default/truepanel-mission-control`.
OBSERVATORY requires the token to live in a separate private file.

A suitable location is:

```text
/var/lib/truepanel/observatory/plex-token
```

Create the directory and token file with private permissions. Reading the token
interactively avoids placing it directly in shell history:

```bash
install -d -m 0700 /var/lib/truepanel/observatory
umask 077
read -r -s -p 'Plex token: ' PLEX_TOKEN; echo
printf '%s\n' "$PLEX_TOKEN" > /var/lib/truepanel/observatory/plex-token
unset PLEX_TOKEN
chmod 0600 /var/lib/truepanel/observatory/plex-token
```

Then add only the non-secret endpoint and token-file path to
`/etc/default/truepanel-mission-control`:

```bash
TRUEPANEL_OBSERVATORY_PLEX_URL=http://127.0.0.1:32400
TRUEPANEL_OBSERVATORY_PLEX_TOKEN_FILE=/var/lib/truepanel/observatory/plex-token
```

The token-file gate is fail closed. The Plex provider is reported unavailable
when the path is relative, missing, a symlink, not a regular file, empty,
unreadable, oversized, or has any group/other permission bits. These failures
do not prevent Mission Control from starting.

The actual Plex URL depends on the Plex deployment/network topology. Do not
assume `127.0.0.1:32400` is correct for every TrueNAS application layout.

## Mission Control contract

Production Mission Control uses `ObservatorySnapshotService`, which enriches the
normal status snapshot with an `activity` block. Core status collection still
fails or succeeds according to its existing contract; only OBSERVATORY-specific
provider/registry failures are contained by the activity boundary.

The activity block declares:

- `project: OBSERVATORY`
- `read_only: true`
- `production_mutation: false`
- provider availability
- bounded normalized observations
- explicit truncation state

GLASS COCKPIT consumes the existing shared `truepanel:status` browser event. It
does not create a second polling loop.

CURRENT ACTIVITY distinguishes three states:

- active evidence, for example `ZFS scrub • 60%`
- `NO OBSERVED ACTIVITY` when OBSERVATORY is available but has no active evidence
- `ACTIVITY UNAVAILABLE` when the activity block itself is absent/unavailable

The annunciator retains the existing mobile collapse and reduced-motion gates.

## HoloDeck proof

HoloDeck scenarios can replay `zfs_activity` over deterministic time. The
rehearsal path uses the same `ZfsActivityProvider` interpreter as live status
rather than a simulator-only activity parser.

The current scrub rehearsal proves:

```text
T+00  idle
T+05  scrub 25%
T+10  scrub 60%
T+15  idle
```

Malformed simulated activity evidence remains dark instead of being coerced
into a positive workload assertion.

## Safety boundaries

OBSERVATORY does not:

- issue ZFS maintenance or repair commands
- control Plex
- control fans or thermal policy
- control LCD/LED hardware
- alter AEGIS incident authority
- grant ORACLE control authority
- place credentials in normalized activity payloads
- guess activity from malformed evidence

## Next gate

ORACLE consumption is deliberately deferred until the activity API and cockpit
presentation have completed their own CI and live guarded validation. When that
gate opens, activity context can be correlated with CPU, drive temperature, fan
behavior, and other telemetry without changing the underlying safety authority.
