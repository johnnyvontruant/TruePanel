# AEGIS Airworthiness Envelope

## Purpose

Project AIRWORTHINESS prevents an old success from silently becoming a current
claim. It continuously compares AEGIS's running reliability contracts with a
versioned, expiring acceptance envelope. A previous production acceptance is
historical evidence; it is not permanent authority.

The envelope binds:

- the accepted TruePanel and TrueNAS release scope;
- the incident-correlation policy ID;
- the complete Recovery Coverage Matrix digest;
- five runtime safety subjects by SHA-256;
- three governed acceptance/calibration artifacts by SHA-256; and
- an issue and expiry time.

It grants no control authority and never suppresses alerts or recovery
guidance.

## States

`CURRENT` requires every runtime subject and policy contract to match, complete
recovery coverage, a sane clock, fresh acceptance evidence, and an explicitly
observed matching TrueNAS release.

`REVIEW` means no known contract has drifted, but a required live fact is not
available. The initial production behavior is intentionally `REVIEW` until the
existing collector supplies an explicit `system.truenas_version`; AEGIS does
not infer the appliance release from a Linux kernel string.

`HOLD` means at least one known fact differs, the envelope expired, the clock
predates the evidence, recovery coverage changed, or a bound subject no longer
matches. HOLD changes only the trust presentation. Raw evidence and guidance
remain available.

## Deterministic proof

`truepanel.holodeck.aegis_assurance.run_airworthiness_rehearsal()` exercises
eight cases against identical packaged contracts:

- accepted envelope: CURRENT;
- platform version unavailable: REVIEW;
- platform version drift: HOLD;
- correlation policy drift: HOLD;
- Recovery Coverage Matrix drift: HOLD;
- runtime subject digest drift: HOLD;
- expired acceptance evidence: HOLD; and
- clock rollback before the accepted evidence: HOLD.

The proof is hardware-isolated and performs no deployment, configuration,
credential, service, storage, network, or hardware operation. Its preserved
result is `docs/evidence/aegis-airworthiness-envelope-v1.json`.

## CI contract

Runtime subjects are checked from the installed package. Evidence documents
remain in their canonical documentation locations and are checked by
`validate_repository_evidence()`. Installed-wheel smoke verifies that the
envelope and rehearsal survive packaging.

Any intentional change to a bound subject must therefore produce a newly
reviewed envelope rather than editing around a failed digest check. The
previous envelope and evidence remain historical HANGAR records.

## Mission Control

Mission Control adds a compact, always-visible AIRWORTHINESS strip under the
active incident summary. It shows the current state, validated platform scope,
review deadline, and plain-language outcome. Individual conditions are
progressively disclosed. At 760 CSS pixels and below the strip and condition
grid reflow to one column; the disclosure target remains at least 44 pixels.

The view consumes the existing shared `truepanel:status` event and introduces
no polling or write route.

## Prior art and provenance

- [Kubernetes conditions](https://kubernetes.io/docs/concepts/workloads/pods/pod-condition/)
  separate condition status, machine-readable reason, message, and transition
  time. TruePanel adapts the status/reason/message semantics.
- [The Update Framework specification](https://theupdateframework.io/specification/v1.0.20/)
  demonstrates why trusted metadata needs versions, expiration, and subject
  hashes. TruePanel adapts these ideas without implementing TUF signing or
  update transport.
- [in-toto Statement v1](https://in-toto.io/Statement/v1) binds attestations to
  immutable subjects by digest. TruePanel uses the subject-digest shape for a
  local validation envelope, not as an in-toto attestation claim.
- [SLSA provenance](https://slsa.dev/spec/v1.0/provenance) reinforces that
  verification must identify which artifact and process produced evidence.

No Kubernetes, TUF, in-toto, or SLSA source code, dependency, signing key,
service, or hosted verifier is incorporated. The implementation is original
MIT-licensed TruePanel code behind a replaceable local interface.

## Rejected and deferred routes

- **Permanent production-valid badge:** rejected because acceptance becomes
  misleading after code, platform, policy, or evidence drift.
- **Kernel-string version inference:** rejected because a kernel build does not
  authoritatively identify the TrueNAS product release.
- **Self-updating envelope:** rejected because software must not rewrite the
  evidence against which it is being checked.
- **Alert suppression on HOLD:** rejected because assurance failure must not
  hide current safety evidence.
- **TUF/in-toto runtime dependency and signing:** deferred. Their full trust
  models are valuable but disproportionate until TruePanel has a governed key
  lifecycle and release-attestation pipeline.

## Strongest follow-up

Expose the TrueNAS release through the already-supported passive API/collector
boundary, then rehearse an upgrade from 25.10.5 in HoloDeck. A release change
must produce REVIEW/HOLD until the recovery matrix, policy, passive providers,
and key scenarios are revalidated and a new immutable envelope is issued.
