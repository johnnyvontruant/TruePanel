# AEGIS verifier confirmation handoff

Status: development-only, simulation-proven, not accepted, not deployed  
Reviewed: 2026-10-03  
Branch: `feature/aegis-verifier-comparison-handoff`  
Dependency: draft PR #187 at `318f01c3e0174272b8b2b60eb5fd52eaa79e2c91`, transitively dependent on frozen baseline PR #78

## Result

The verifier comparison path now persists its short-lived public receipt as a
new owner-protected two-file handoff and re-audits the pinned verifier release,
the complete comparison kit, the receipt, its manifest, and its 30-minute
validity before the field ceremony may consume it.

The review found and closed a more important predecessor gap: an internally
consistent challenge, card, and manifest could describe a different verifier
release. Kit audit and confirmation now require the reviewed release receipt
and verifier source and compare the complete challenge with a freshly
reconstructed release-bound challenge. A coherent foreign kit therefore
produces `HOLD`.

Success means only `VERIFIER_CONFIRMATION_HANDOFF_VERIFIED`. The existing
field coordinator then reaches `ACTION_REQUIRED_PUBLIC_ROSTER`; it does not
create a roster, key, signature, production acceptance, deployment, or live
action.

## Architecture and custody contract

The handoff contains only:

- `aegis-verifier-confirmation-receipt.json`: canonical public operator attestation;
- `manifest.json`: hashes and identifiers binding that receipt to all three audited kit views.

The output directory is new, absolute, owner-only (`0700`), and non-overwriting.
Both files are created exclusively as `0600`, written completely, and fsynced.
Audit requires the exact file set, refuses symlinks and special/changing files,
reconstructs the manifest, reconstructs the receipt from the release-bound kit,
re-verifies the source and release receipt, and checks expiry at the consumer's
observation time.

The manifest is not an authenticity root. Because this is an unsigned
single-operator attestation, coordinated replacement by an actor who can also
rewrite all handoff material cannot be attributed to JT. The later protected
development SSHSIG remains the cryptographic operator-identity boundary.

## HoloDeck evidence

`docs/evidence/aegis-verifier-confirmation-handoff-v1.json` preserves 16 scenarios:

- 1 release-bound handoff verified;
- 1 field-ceremony transition to `ACTION_REQUIRED_PUBLIC_ROSTER`;
- 12 `HOLD` results covering a coherent foreign kit, receipt/manifest/authority
  substitution, extra/missing/symlinked files, expiry, post-staging kit drift,
  verifier-source drift, relative custody, and occupied output;
- 2 denied constructions covering the wrong independently observed digest and
  a same-repository channel;
- 0 accepted foreign kits, private-key inputs, signer calls, cryptographic
  independence claims, production acceptances, deployments, hardware actions,
  or runtime writes.

The accepted Recovery Coverage Matrix remains 8/8 trusted with 0 gaps.

## Prior-Art Field Report

The strongest candidates were inspected in their actual specifications or
source rather than only through project descriptions.

| Candidate | What it supplies | Maturity / maintenance / tests | Platform fit and weight | Security and license | Recommendation / time saved |
|---|---|---|---|---|---|
| [Sigstore Bundle](https://github.com/sigstore/protobuf-specs/blob/main/protos/sigstore_bundle.proto) | One portable object that binds content and verification material; requires clients to verify embedded material against independent trust roots | Active ecosystem specification with generated implementations and conformance work | Strong conceptual fit, but protobuf, transparency-log, certificate, and trust-root machinery are excessive for this unsigned local gate | Apache-2.0; attribution required if code is copied. No code copied | Adapt the bundle/verification-material separation; defer runtime adoption. Saved the design pass for separating public receipt, manifest, and independent trust |
| [Git tempfile API](https://github.com/git/git/blob/master/tempfile.h) | Complete-write/cleanup/atomic-rename lifecycle and explicit occupied-output behavior | Decades of production use and extensive Git regression coverage | Native implementation is C and Git-specific; semantics transfer cleanly to small standard-library code | GPL-2.0-only implementation; incompatible for copying into this project. Ideas and documented OS semantics only | Adapt exclusive creation, complete writes, cleanup, and non-overwrite behavior; do not adopt code |
| [in-toto Statement v1](https://github.com/in-toto/attestation/blob/main/spec/v1/statement.md) | Digest-bound immutable subjects and typed predicates | Active specification, maintained libraries, cross-ecosystem use | Useful schema discipline; adopting the framework would add unnecessary envelope/signature dependencies before JT's SSHSIG gate | Specification and implementations have separate licenses; no schema or code copied | Adapt subject-by-digest semantics. A full dependency would save little because this receipt is deliberately unsigned and local |
| [TUF specification](https://github.com/theupdateframework/specification/blob/master/tuf-spec.md) | Versioned metadata, consistent snapshots, expiry, and trust anchored outside the delivered bundle | CNCF-graduated design, active 1.0 specification and reference implementations | Excellent threat-model fit; full updater stack is unrelated and heavy | Community Specification License 1.0 for the specification; implementations vary. No code copied | Adapt fixed observation time, expiry, and independent-root separation; do not adopt runtime |

### Build versus adopt

Build the small TruePanel-owned adapter. Existing frameworks assume signatures,
certificate chains, transparency services, repository roles, or update clients.
Adding one would enlarge the dependency and trust surface before the operator
has even provisioned a public development key. The useful shortcut is their
shared invariant: a portable bundle is evidence, not its own independent trust
root, and consumers must verify the exact subject, freshness, and trust material.

### Rejected paths

- Keep printing the receipt to stdout and rely on shell redirection: permits
  truncation, accidental overwrite, and unclear custody.
- Trust an internally consistent comparison kit without rechecking the pinned
  release: accepts a coherent but foreign verifier identity.
- Treat the handoff manifest as authentication: coordinated unsigned replacement
  remains possible.
- Add Sigstore, in-toto, or TUF runtimes now: dependency weight and unrelated
  services exceed the verified development time saved.
- Copy Git's tempfile implementation: license and language mismatch, and the
  standard library already supplies the required primitives.
- Add a signer or private-key convenience path: violates the operator-owned-key
  boundary.

### Best collaboration opportunity

The Sigstore bundle and TUF maintainer communities are the strongest people for
JT to approach about reviewable offline verification material and honest
independent-root bootstrapping for a small single-operator system. External
contact was not attempted.

## Safety and open risks

No production or hardware authority is introduced. The handoff is public
development evidence and still depends on JT honestly obtaining the verifier
digest through one approved independent channel. It is not a signature and
cannot authenticate JT. The full AEGIS stack remains a draft dependency chain;
changes to any predecessor invalidate the content-bound evidence and require a
new rehearsal.

No merge, deployment, BattleStation access, service or configuration change,
credential handling, boot-task change, storage/network mutation, or fan/LCD/
bay-LED/hardware actuation is performed.

## Strongest next step

Export and audit one real comparison kit, let JT obtain and compare the verifier
SHA-256 through an operator-controlled channel, stage this short-lived public
handoff, and allow the read-only coordinator to name the protected public-roster
gate. Do not create or import a private key.
