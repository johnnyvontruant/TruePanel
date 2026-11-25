# AEGIS public-only temperature signing kit

## Outcome

This increment closes the transport gap between the authenticated temperature
acceptance in PR #206 and JT's eventual offline SSHSIG ceremony. It exports
exactly three public files to a new operator-selected directory outside the
source checkout, accepts only a protected detached signature on return, and
reconstructs every reviewed subject before verification.

Success is intentionally narrow:
`AUTHENTICATED_DEVELOPMENT_ACCEPTED_FOR_REVIEW`. It does not accept or install
the 9/9 candidate, mutate the accepted 8/8 Recovery Coverage Matrix, deploy
software, write storage or network state, or actuate hardware.

## Architecture and safety contract

`export_temperature_signing_kit` creates a mode-0700 directory and three
mode-0600 files using exclusive, no-follow descriptors and complete-write
loops:

- `statement.json`: the canonical content-bound statement from PR #206;
- `manifest.json`: exact statement and instructions digests, signer,
  namespace, scope, and explicit no-authority fields;
- `SIGNING.txt`: a human-readable digest card and offline signing boundary.

The exporter refuses relative paths, existing outputs, symlinks, and any output
inside the source checkout. A failed export removes partial files. It has no
private-key parameter and no signer implementation.

`verify_temperature_signing_return` requires the exact three-file set, reads
every public file and the returned signature through owner-controlled,
non-symlinked descriptors, detects files that change during reading,
reconstructs the current statement and manifest, and delegates only
verification to the existing TruePanel-owned `OpenSshSignatureVerifier`.

Mission Control exposes the public-kit and return-verification state on the
mobile reliability panel and states that TruePanel never receives the private
key. The live view remains blocked at operator confirmation; it does not invent
a kit, key, or signature.

## HoloDeck evidence

TP-EXP-0027 preserves twelve deterministic cases: one public-only kit is ready
for offline signature, one disposable Ed25519 SSHSIG return authenticates for
development review, and ten cases hold for occupied or in-checkout output,
symlinked kit or signature, statement or manifest tampering, unexpected files,
unsafe permissions, invalid signatures, and expired confirmation. TruePanel
accepts zero private-key inputs and invokes zero signers. The disposable fixture
key is removed. Runtime acceptances, candidate installations, deployments,
hardware actions, and runtime writes remain zero.

Preserved evidence:
`docs/evidence/aegis-temperature-signing-kit-v1.json`, self-digest
`81cff4a05e10a1df9349c7488a095fa9f5e24053705482cd512f045b31332a74`.

## Prior-Art Field Report

Actual upstream protocols, documentation, and tests were inspected on
2026-10-12 rather than relying on project descriptions.

| Candidate | What the inspected work supplies | Fit, maturity, dependency and security | License / attribution | Decision |
| --- | --- | --- | --- | --- |
| [OpenSSH SSHSIG protocol](https://github.com/openssh/openssh-portable/blob/master/PROTOCOL.sshsig) and [negative regression suite](https://github.com/openssh/openssh-portable/blob/master/regress/sshsig.sh) | Detached armored signatures, namespaces, hashed messages, and principal/wrong-key/data/namespace negative tests | Mature installed tool, active upstream work, no new runtime package; namespace prevents cross-protocol reuse. TruePanel's narrower roster rejects wildcard/options complexity. | BSD-style / public-domain components; no code copied. The installed executable remains behind a TruePanel interface. | **Adopt the verifier and protocol; adapt the negative-test model.** |
| [in-toto Statement v1](https://github.com/in-toto/attestation/blob/main/spec/v1/statement.md) | Immutable subjects identified by digests and an unambiguous statement type | Strong portable attestation model and active ecosystem. Another verifier/schema dependency is unnecessary for a three-file local handoff. | Specification CC-BY 4.0; concept cited, no schema or code copied. | **Adapt digest-bound subjects and strict reconstruction.** |
| [Minisign](https://github.com/jedisct1/minisign) | Small Ed25519 file-signing workflow, detached signatures, cross-platform implementations | Focused and mature, but adds another key format and executable while OpenSSH is present. Its simple UX validates the public-message/detached-return shape. | ISC license; no code or dependency incorporated. | **Defer.** A future portable client could implement the TruePanel interface. |
| [Cosign signature specification](https://github.com/sigstore/cosign/blob/main/specs/SIGNATURE_SPEC.md) | Detached payloads, offline bundles, certificate and transparency-log integrations | Excellent for public OCI release provenance, but materially heavier than a local operator ceremony and may add online identity/log dependencies. | Apache-2.0; no code, service, package, or schema incorporated. | **Defer until TruePanel distributes signed release artifacts.** |
| [The Update Framework specification](https://github.com/theupdateframework/specification/blob/master/tuf-spec.md) | Offline roles, expiration, rollback/freeze resistance, and separation of trusted metadata from installation | Mature CNCF design. Full TUF is excessive here, but its authority separation supports the rule that authenticated metadata is not installation authority. | Specification CC-BY 4.0; concepts cited, no code copied. | **Adapt expiration and authority separation only.** |

Reuse the installed OpenSSH verifier and keep TruePanel's exporter and strict
manifest reconstruction small and owned. This avoids a new cryptographic
library, key format, signing service, transparency service, or credential path.
No third-party code, package, schema, credential, key, service, or dataset was
added. OpenSSH maintainers remain the strongest collaboration opportunity,
particularly around portable SSHSIG verification and adversarial vectors.

## Failed paths and challenged assumptions

- Writing into the repository would make a ceremony artifact look like source
  and allow checkout drift to confuse review, so it is rejected.
- A valid detached signature does not make adjacent manifest and instructions
  trustworthy; all three public files are reconstructed.
- Reusing an output directory makes stale-file reuse ambiguous; export requires
  a new path.
- A high-level write may be partial. The exporter loops until completion,
  flushes files, and removes partial exports on failure.
- Convenience signing would pull private-key inputs into TruePanel. No signing
  API exists.

## Open risks and next gate

No real JT public roster or signature exists, and the HoloDeck clock is a
deterministic fixture. The next gate is JT provisioning only the protected
development public roster, exporting one exact kit from the pinned checkout,
comparing its digest and trusted UTC, signing `statement.json` offline, and
returning only the detached signature for read-only verification. Any candidate
installation or production deployment remains a separate future proposal.
