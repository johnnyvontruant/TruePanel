# AEGIS Identity Coverage Checkride

Reviewed 2026-09-15. This increment makes stable drive identity an explicit
candidate condition for every storage recovery without changing the accepted
Recovery Coverage Matrix or its airworthiness envelope.

## Architecture decision

The accepted v1 matrix is a SHA-256-bound airworthiness subject. Editing it in
place would correctly put the accepted envelope into `HOLD`. TruePanel therefore
builds a read-only v2 candidate beside v1, binds it to the canonical digest of
its predecessor, rehearses it, and exposes only `READY_FOR_OPERATOR_REVIEW`.
It cannot accept itself. Independent review and a successor envelope remain
mandatory.

The candidate adds identity-continuity contracts to:

- `storage.smart_warning`
- `storage.disk_faulted`
- `storage.pool_degraded`

Each requires a privacy-safe serial-model, ZFS-member, or WWN identity and the
`aegis-stable-identity-migration` regression. The evaluator permits an identity
change only when the successor is strictly stronger and Lifeline preserves the
old session and fault keys as explicit lineage. It rejects cloned identities,
one path assigned to different identities, scope drift, weak evidence, and
missing lineage.

## HoloDeck evidence

The checkride uses the real `LifelineSessionStore` in a disposable directory.
It performs six deterministic scenarios: three trusted and three expected
holds. Serial-model to WWN migration across `/dev/sdc` to `/dev/sda` preserves
one active recovery session; two different WWNs in the same bay remain two
sessions; weaker evidence cannot downgrade WWN. Missing lineage, a cloned
identity, and runtime-path reuse all hold. There are zero false outcomes, zero
raw identifiers retained, zero telemetry reads, and zero production writes.

Evidence: `docs/evidence/aegis-identity-coverage-v1.json`.

## Prior-Art Field Report

| Candidate | What the implementation supplies | Fit and maturity | License / obligations | Decision |
|---|---|---|---|---|
| [systemd persistent-storage rules](https://github.com/systemd/systemd/blob/main/rules.d/60-persistent-storage.rules.in) | Concrete WWN, serial, UUID, and path naming hierarchy across major Linux storage transports | Mature and directly relevant, but udev names are platform evidence rather than a recovery ledger | LGPL-2.1-or-later; copying would require license compliance | Adapt the precedence idea; keep TruePanel's opaque identity interface |
| [OpenZFS vdev identity](https://github.com/openzfs/zfs/blob/master/include/sys/vdev_impl.h) | A `vdev_guid` distinct from child position, plus explicit vdev topology | Best platform-native long-term identity for ZFS membership; supported TrueNAS read-only exposure still needs confirmation | CDDL-1.0; no code copied | Pursue a supported passive leaf-vdev GUID through TrueNAS/OpenZFS maintainers |
| [Kubernetes object UIDs](https://kubernetes.io/docs/concepts/overview/working-with-objects/names/#uids) | Separates a reusable human name from a unique object incarnation | Mature architectural precedent for avoiding name/path reuse confusion | Documentation and project content are CC BY 4.0 / Apache-2.0 as applicable; attribution required if copied | Adapt incarnation-versus-address semantics only |
| [TUF specification](https://theupdateframework.github.io/specification/latest/) | Content binding, versioned trust transitions, threshold review, and rollback resistance | Mature CNCF specification; heavier than the identity problem itself | Community Specification License 1.0; no code copied | Adapt predecessor binding and separately reviewed promotion |
| [OpenTelemetry service instance identity](https://opentelemetry.io/docs/specs/semconv/resource/#service) | Common correlation vocabulary separating a service namespace/name from an instance | Mature for software telemetry, but does not resolve physical disks or replacements | Apache-2.0; attribution/notice if code were incorporated | Inspiration only; do not add its SDK for this narrow contract |

The strongest shortcut is not a new dependency. It is the already-integrated
Lifeline migration ledger combined with explicit predecessor lineage and a
small TruePanel-owned evaluator. This avoids a second hardware poller, new
credentials, raw serial persistence, and a heavyweight RCA framework. No
external code, schema, package, hosted service, key, credential, or dataset was
incorporated.

The most promising collaboration is with OpenZFS and TrueNAS middleware
maintainers: establish a documented, read-only leaf-vdev GUID observation that
can be joined to existing privacy-safe drive evidence. That could reduce
platform-specific inference while retaining TruePanel's replaceable adapter.

## Rejected paths and lessons

- Linux `/dev/*` paths and by-path names are addresses, not drive identity.
- Bay alone identifies a location and would merge a replacement with its
  predecessor.
- Raw serials and WWNs in UI or preserved evidence create unnecessary privacy
  and support risk.
- Equal-strength key changes cannot be selected automatically; ambiguity holds.
- Importing Kubernetes, TUF, OpenTelemetry, or an RCA stack would add far more
  dependency and attack surface than this contract requires.
- Directly editing the accepted v1 matrix would bypass the intended review
  boundary and invalidate current airworthiness. The candidate remains
  separately visible and explicitly unaccepted.

## Build versus adopt

Build the small identity-continuity policy locally; adopt only documented
platform observations behind Lifeline's interface. Reassess a ZFS-GUID adapter
when TrueNAS exposes a supported passive contract. Promote the v2 matrix only
through the existing two-person review, witnessed-stage, and successor-envelope
workflow.
