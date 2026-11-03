# AEGIS Temperature Field-Review Receipt

Reviewed 2026-10-15. This increment is stacked on PR #209 and remains
simulation-only. It does not alter the accepted 8/8 Recovery Coverage Matrix,
install the temperature candidate, validate field behavior, deploy software, or
grant storage, network, fan, LCD, bay-LED, or other hardware authority.

## The gap

PR #209 safely snapshots and replays one bounded recording, but its field-shaped
path still receives `operator_opt_in` and `incident_reviewed` as caller-supplied
booleans. Those values describe review; they do not prove which bytes JT
reviewed. A valid development signature also cannot be reused as a field-review
signature because the two decisions have different meaning.

This increment exports a public-only review kit after the protected recording
and development SSHSIG pass. JT's future detached SSHSIG covers a canonical
statement binding the exact recording digest, byte count and frame count; the
development authentication record; privacy and incident-outcome review; a
two-hour expiry; and every negative authority claim. Verification reconstructs
the statement and replays intake after checking the signature. Success means
only `FIELD_OBSERVATION_ACCEPTED_FOR_REVIEW`.

The review verifier must use the same protected roster file and Ed25519
fingerprint as the development verifier. A distinct namespace prevents
cross-purpose replay, but namespace separation alone is not a trust root.

## Preserved proof

`TP-EXP-0030` preserves 12 deterministic scenarios: one public kit ready for
offline signing, two content-bound calibration-review results (immediate and
delayed within the valid window), and nine HOLD
results. Wrong namespace, a foreign key under the same principal, invalid
signature, recording drift, authority escalation, manifest substitution,
unsafe permissions, extra files, and expiry all fail closed. Unsafe-ready
outcomes, private-key inputs, TruePanel signer invocations, field validations,
acceptances, installations, deployments, hardware actions, and runtime writes
are all zero.

Evidence: `docs/evidence/aegis-temperature-field-review-receipt-v1.json`
(file SHA-256 `1d696bfc4d68ef0893352f2f2412dc3c452016075fb23913f9806083a9ef26e2`).

## Prior-Art Field Report

The following upstream code and specifications were inspected directly rather
than inferred from project summaries.

| Candidate | What it supplies | Maturity / tests / fit | Dependency and security posture | License / attribution | Decision |
|---|---|---|---|---|---|
| [OpenSSH SSHSIG protocol](https://github.com/openssh/openssh-portable/blob/master/PROTOCOL.sshsig) and [regression suite](https://github.com/openssh/openssh-portable/blob/master/regress/sshsig.sh) | Detached signatures, explicit namespaces, allowed-signers verification, negative cases for wrong key, principal, data, and namespace | Mature, maintained, already installed, with broad upstream regression coverage; exact platform fit | No Python dependency or network service; private key remains outside TruePanel | BSD-family / permissive OpenSSH terms; protocol use requires no copied notice | **Adopt installed verifier behind TruePanel interface.** This is the largest verified time saving. |
| [DSSE protocol 1.0.2](https://github.com/secure-systems-lab/dsse/blob/master/protocol.md) | Pre-authentication encoding binds payload type and exact serialized body; warns that key IDs are unauthenticated hints | Stable protocol with vectors and implementations; valuable semantic model | Adding an envelope implementation now would duplicate SSHSIG domain separation and enlarge parsing surface | Apache-2.0; notice required if code is copied | **Adapt the idea only.** Canonical schema + SSHSIG namespace provide the needed domain separation without another envelope dependency. |
| [in-toto Statement v1](https://github.com/in-toto/attestation/blob/main/spec/v1/statement.md) | Immutable subjects identified by digest and a typed predicate | Widely used supply-chain schema; excellent subject/predicate model | Generic attestation dependency would add schema and packaging weight to a narrow local ceremony | Apache-2.0; preserve license/notice if code or schema is copied | **Architectural inspiration.** Bind immutable recording and authentication subjects, but retain a TruePanel-owned replaceable schema. |
| [TUF specification 1.0.37](https://github.com/theupdateframework/specification/blob/master/tuf-spec.md) | Separates trusted root material, roles, expiry, and application action | CNCF-backed specification, current on 2026-10-08; strong trust-root and expiry semantics | Full update framework is unnecessary because this receipt neither distributes nor installs artifacts | Community Specification License 1.0; implementations need no spec attribution, derivative spec text does | **Adapt trust-root and expiry concepts only.** The same protected roster anchors both ceremonies. |
| [SLSA attestation model](https://github.com/slsa-framework/slsa/blob/main/spec/attestation-model.md) | Layers authenticated statements, immutable subjects, predicates, and bundles | Current OpenSSF specification with a broad policy-engine ecosystem | Does not solve offline operator intent or local protected-roster handling | Community Specification License 1.0; implementations need no copied spec notice | **Reference only.** TruePanel needs a narrower operator review record. |

### Build-versus-adopt conclusion

Reuse OpenSSH's installed verifier and external signing protocol. Keep file
protection, trust-root pinning, canonical statement construction, replay, and
authority semantics in a small TruePanel-owned adapter. No third-party source,
schema, package, service, credential, public key, private key, or dataset was
copied or added. The report links and names the ideas used; there is no new
runtime attribution obligation.

The most promising collaboration is with OpenSSH maintainers: their SSHSIG
protocol and negative suite already cover the cryptographic primitive TruePanel
needs, while TruePanel can contribute experience from a constrained offline
operator-review workflow. Contacting maintainers remains outside this work.

## Rejected and failed paths

- Reusing the development signature was rejected because it authenticates a
  different decision and would make cross-purpose replay possible.
- Trusting `key_id` or principal name alone failed review: a replacement roster
  could authorize another key under the same name. The exact roster and
  fingerprint are now pinned.
- DSSE or in-toto packages were not added because they do not replace protected
  file I/O, key trust, expiry, or application policy, and would increase the
  replaceability and dependency burden.
- A convenience signer remains rejected. TruePanel accepts no private-key path
  and invokes no signing command.
- A successful review receipt is deliberately not called field validation. It
  admits evidence to calibration review and nothing more.

## Next gate

JT provisions only the protected development public roster, returns the
development-only SSHSIG, and supplies one separately governed sanitized
recording. TruePanel can then export the exact field-review statement for JT to
inspect and sign offline. Any later field-validation, candidate acceptance,
installation, or deployment decision remains a separate design and review.
