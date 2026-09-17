# AEGIS Identity Coverage Review Handoff

## Outcome

This increment creates the independent-review boundary between the appraised
Recovery Coverage Matrix v2 candidate and any future successor AIRWORTHINESS
envelope.  It does **not** review, accept, install, or promote that candidate.

The portable packet binds the accepted v1 matrix, complete v2 candidate,
appraisal result, and appraisal policy.  A receipt is eligible only after two
distinct, current Ed25519 reviewer keys verify the same canonical statement in
the fixed `truepanel-aegis-review-v1@truepanel` SSHSIG namespace.  Receipts
expire within 24 hours.  Success means only
`ELIGIBLE_FOR_SUCCESSOR_ENVELOPE_DRAFT`.

The normal Mission Control state is deliberately
`AWAITING_INDEPENDENT_SIGNATURES`: TruePanel ships no production reviewer key,
private key, signer, or acceptance authority.

## Prior-art field report

Research was refreshed on 2026-09-17 and included actual specifications and
implementation sources, not project descriptions alone.

| Candidate | Useful capability | Maturity / maintenance | Fit and weight | License / obligations | Decision |
|---|---|---|---|---|---|
| [OpenSSH SSHSIG](https://github.com/openssh/openssh-portable/blob/master/PROTOCOL.sshsig) and [`ssh-keygen -Y`](https://man.openbsd.org/ssh-keygen.1) | Detached signatures, explicit application namespace, system public-key tooling | Mature; portable repository was active on 2026-09-16 | Excellent on TrueNAS/Linux; no Python crypto dependency; system executable isolated behind `OpenSshSignatureVerifier` | OpenSSH's BSD/ISC-style notices apply to OpenSSH itself; no code was copied or redistributed | **Adopt the installed verifier contract.** Reuse TruePanel's existing narrow adapter and exact Ed25519 roster profile. |
| [in-toto layout model](https://github.com/in-toto/in-toto/blob/develop/in_toto/models/layout.py) | Named functionaries, expiration, signed layouts, per-step thresholds | Active on 2026-08-27; established supply-chain project with tests | Strong semantic fit, but its Python stack and general supply-chain model exceed this one review decision | Apache-2.0; notice and license obligations if code is incorporated | **Adapt concepts only.** The packet/subjects split and independent functionaries are valuable; the runtime dependency is not. |
| [TUF threshold roles](https://theupdateframework.github.io/specification/latest/) / [python-tuf](https://github.com/theupdateframework/python-tuf) | Threshold keys, offline roots, expiration, key lifecycle and revocation | Specification updated 2026-08-05; python-tuf active 2026-09-15 with conformance tests | Excellent trust-transition model; repository/update machinery is unnecessary for this bounded decision | Specification uses Community Specification License 1.0; python-tuf is MIT | **Adapt threshold and freshness semantics only.** Do not turn Recovery Coverage review into an update repository. |
| [Sigstore Cosign](https://github.com/sigstore/cosign) | Identity-bound signing, bundles, transparency-log proof, keyless workflows | Highly active on 2026-09-15; broad test and ecosystem coverage | Powerful but adds binary/runtime, identity-provider, root, privacy, and offline-governance decisions | Apache-2.0 with dependency notices | **Defer.** Reconsider if JT chooses public workload identity and transparency as explicit policy. |
| GitHub protected environments | Named reviewers and deployment gates | Mature hosted service | Useful operational analogy, but review truth would depend on a hosted control plane and does not bind the local candidate packet by itself | Service terms, no code incorporated | **Do not adopt as evidence.** It may coordinate humans later, but cannot replace content signatures. |

### Reusable code versus ideas

No external source, schema, library, key, service, credential, or dataset was
incorporated.  TruePanel reuses its already-owned `OpenSshSignatureVerifier`
interface around the system `ssh-keygen` executable.  SSHSIG namespace
separation, TUF-style two-key threshold/freshness, and in-toto-style explicit
subjects were adapted as architectural semantics.

The strongest collaboration opportunity is the OpenSSH portable project: JT
could validate the long-term portability of memory-backed allowed-signers and
signature inputs on the exact TrueNAS base.  A secondary opportunity is the
in-toto/SLSA community if TruePanel later wants its review packet to interoperate
with a standard attestation envelope.

## HoloDeck checkride

Disposable Ed25519 keys exist only inside an automatically removed HoloDeck
directory.  Nine scenarios produced one eligible result and eight holds:

- exact two-reviewer quorum: eligible to draft, with no further authority;
- one reviewer and duplicated reviewer: hold;
- expired receipt: hold;
- unsigned packet extension and candidate tamper: hold;
- SSHSIG namespace mismatch and unsafe roster permissions: hold;
- duplicate reviewer identity in policy: hold.

False outcomes, false eligibility, candidate acceptances, successor envelopes,
runtime writes, and production writes were all zero.  Evidence is preserved at
`docs/evidence/aegis-identity-review-v1.json` with SHA-256
`aaddd3dca8c27c104ab7890fadb4c2bc960bff57765ff7b6205020c3701f1406`.

## Rejected and failed paths

- Reusing the older promotion receipt directly was rejected because its
  success state authorizes operator promotion and its appraisal status is for
  successor envelopes, not Recovery Coverage candidates.
- A bundled signer was rejected: TruePanel must not possess reviewer private
  keys or collapse review and implementation authority.
- Hash-only approval was rejected because integrity is not reviewer
  authentication.
- One key with two labels, wildcard principals, certificate-authority roster
  options, and duplicate reviewers were rejected because they defeat separation
  of duty.
- A long-lived receipt was rejected because a stale review could cross later
  candidate or policy changes.
- in-toto, python-tuf, and Cosign runtime dependencies were rejected for this
  increment because the existing OpenSSH adapter provides the exact required
  verification primitive with less attack surface and no new package.

## Open risks and next step

This is deterministic lab proof, not a completed operator review.  Real use
still requires two independently controlled Ed25519 public keys, a protected
exact roster, reviewer identity/lifecycle policy, and signatures over the
published packet.  The current PR remains stacked on unmerged #155 and #157;
any predecessor change invalidates the packet.

After operator-owned review exists, the next increment should construct a
successor AIRWORTHINESS envelope draft binding the reviewed v2 matrix and new
evaluator, then rehearse ZFS-member to WWN migration.  Drafting, acceptance,
installation, and deployment must remain separate decisions.
