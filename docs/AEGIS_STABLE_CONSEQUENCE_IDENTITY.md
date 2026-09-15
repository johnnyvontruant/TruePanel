# AEGIS stable consequence identity

Reviewed 2026-09-14 against accepted `main` at `f4ef8fda`.

## Outcome

AEGIS consequence correlation no longer trusts a Linux `/dev/*` address as a
durable hardware identity. The adapter consumes the Lifeline evidence already
present in the shared Mission Control snapshot and joins an AEGIS incident to a
SENTINEL explanation only when both resolve to one trusted opaque identity.

No collector, udev invocation, SMART call, middleware query, graph edge, or
control path was added. The live device addresses remain visible as observed
evidence and every SENTINEL path is still validated against its current source.

## Trust contract

- Only active Lifeline sessions are eligible.
- Only privacy-safe `wwn`, `serial_model`, or `zfs_member` identities with high
  or very-high confidence are accepted.
- The opaque stable key must use the existing Lifeline 24-hex token format.
- Raw serial and WWN exposure flags must both be false.
- Missing identity, multiple identities for one path, one identity claimed by
  multiple active sessions, malformed graph paths, or unsafe subsystem flags
  produce `HOLD`.
- Historical device paths are accepted only while they remain unambiguous.
- Consequence evidence never changes diagnostic confidence and never proves an
  outage, data loss, or application failure.

## HoloDeck evidence

Six deterministic scenarios exercise the identity boundary:

1. Same device address and stable identity: `PROVED`.
2. Incident at `/dev/sdc`, current SENTINEL source at `/dev/sda`, one Lifeline
   identity spanning both observations: `PROVED`.
3. Missing stable identity: `HOLD`.
4. One stable key claimed by two active sessions: `HOLD`.
5. A historical path reused by a different stable identity: `HOLD`.
6. Malformed dependency path despite valid identity: `HOLD`.

Measurements: 2 `PROVED`, 4 `HOLD`, one path reassignment preserved, cloned
identity holds 1, reused-path holds 1, false joins 0, confidence increases 0,
additional telemetry reads 0, recovery actions 0, and control authority false.

Preserved evidence: `docs/evidence/aegis-consequence-correlation-v1.json`.

## Prior-Art Field Report

| Candidate | Inspected capability | Maturity, fit, and weight | License / recommendation |
| --- | --- | --- | --- |
| [systemd persistent-storage rules](https://github.com/systemd/systemd/blob/main/rules.d/60-persistent-storage.rules.in) | Creates `by-id` links from WWN and serial properties, while separately creating topology-oriented `by-path` links. The actual rules also expose a race-resistant `by-diskseq` mechanism. | Mature Linux foundation and already present below TruePanel. Excellent semantics, but importing rule code would duplicate the host's responsibility. | systemd is predominantly LGPL-2.1-or-later. Adopt the identity hierarchy as an interface contract; do not copy or install rules. |
| [OpenZFS vdev identity](https://github.com/openzfs/zfs/blob/master/include/sys/vdev_impl.h) | The inspected implementation declares `vdev_guid` as the unique vdev ID and separately tracks GUID sums and original GUIDs. | Mature and closest to TrueNAS topology. A leaf-vdev GUID exposed through the supported middleware would be a strong independent identity source. Direct kernel/library coupling is inappropriate. | CDDL-1.0. Adapt the stable-GUID idea only; consider a future passive TrueNAS API field behind Lifeline. |
| [smartmontools](https://github.com/smartmontools/smartmontools/blob/master/src/ataprint.cpp) | The actual ATA path handles serial output and structured JSON; smartd also combines model, serial, WWN, firmware, and capacity for device identity. | Mature, hardware-aware, and commonly available, but subprocess parsing would add another observation and raw identifier handling to this join. | GPL-2.0. Continue using existing collectors and Lifeline normalization; do not copy code or add a new invocation. |
| Existing TruePanel Lifeline resolver | Hashes WWN or serial+model, cross-checks inventory, retains path history, hides raw identifiers, and already has rename regression tests. | Native MIT code, tested, zero new runtime weight, and exactly the evidence AEGIS needs. | Adopt directly through the shared snapshot; this saves a new collector and preserves replacement semantics. |

### Build versus adopt

Adopt Lifeline's existing identity record and build only the small fail-closed
index inside AEGIS. systemd, OpenZFS, and smartmontools validate the hierarchy,
but adding their code or another invocation would increase privilege, privacy,
and compatibility surface without improving the already-observed evidence.

No external code, rule, schema, dependency, service, credential, raw hardware
identifier, or dataset was incorporated. The implementation is original
MIT-licensed TruePanel code.

### Rejected paths and failed assumptions

- `/dev/*`, bay number, enclosure path, model, or serial suffix alone: not a
  durable unique identity.
- Accepting Lifeline's `legacy_runtime_address` or medium-confidence correlated
  fallback: too weak for cross-address joins.
- Treating `by-path` as device identity: it identifies a connection location,
  which may later contain a different drive.
- Automatically choosing between duplicate identities: unsafe; ambiguity must
  remain visible.
- Re-running udev, SMART, or TrueNAS middleware from AEGIS: unnecessary polling
  and a second source of truth.
- Persisting or displaying raw serial/WWN values: unnecessary privacy exposure.

## Collaboration opportunity

OpenZFS and TrueNAS middleware maintainers are the strongest prospective
collaboration target: a documented, passive leaf-vdev GUID field would give
Lifeline an independent topology-native identity signal without direct kernel
coupling. JT should approach them about supported identity semantics and field
stability, not request a TruePanel-specific control API.

## Open risk and next step

The current Lifeline session must already exist before consequence correlation
can become `PROVED`; missing identity correctly leaves Mission Control at
`HOLD`. The next step is to add a passive identity-coverage condition to the
Recovery Coverage Matrix and rehearse identity migration from serial-model to
WWN or ZFS GUID without splitting one incident or silently merging two drives.
