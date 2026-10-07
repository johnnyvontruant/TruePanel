# AEGIS signing-kit enrollment binding

## Decision

The field coordinator now compares the identity reconstructed from the complete
public signing kit with the exact key ID and fingerprint reconstructed from JT's
roster enrollment. An internally valid kit for another Ed25519 key cannot reach
the independent-audit or offline-signing instruction, even when it uses the same
`jt-development-review` principal.

The successful state remains
`ACTION_REQUIRED_INDEPENDENT_KIT_AUDIT`. It does not sign, accept a private key,
create an operator identity, promote a candidate, deploy, or control hardware.
The enrollment receipt remains unsigned public evidence; JT's separately
compared fingerprint remains the trust input.

## Failed assumption

The previous composition treated an internally consistent signing kit as safe
to present because returned-signature verification would later reconstruct the
session against the current roster. That was too late: JT could already have
been instructed to inspect and sign a valid kit bound to a different
same-principal key. Final signature rejection is not a substitute for
pre-signing subject binding.

## Prior-Art Field Report

| Candidate | What the inspected implementation supplies | Maturity and fit | License / attribution | Recommendation |
| --- | --- | --- | --- | --- |
| [OpenSSH SSHSIG protocol](https://github.com/openssh/openssh-portable/blob/master/PROTOCOL.sshsig) and [implementation](https://github.com/openssh/openssh-portable/blob/master/sshsig.c) | The signature object carries the public key and namespace; the verifier parses the exact object and rejects unsupported versions. | Mature, installed on target platforms, low dependency weight, strong negative-path history. Excellent final cryptographic verifier, but it cannot prove that an earlier UI showed the enrolled key. | ISC-style OpenBSD permission notice in `sshsig.c`; installed executable only, no copied code. | **Adopt executable behind TruePanel's interface; adapt exact-key and namespace semantics.** |
| [TUF specification](https://github.com/theupdateframework/specification/blob/master/tuf-spec.md) | Clients establish trusted keys and roles before accepting target metadata; metadata consistency prevents mix-and-match substitution. | Mature CNCF security architecture with strong client-side verification concepts. Full TUF is too heavy for one local development-only ceremony. | Community Specification License 1.0 for the spec; no code copied. | **Adapt final-consumer trusted-key reconstruction; do not add a TUF runtime.** |
| [in-toto Statement v1](https://github.com/in-toto/attestation/blob/main/spec/v1/statement.md) | Attestations bind predicates to immutable subjects by digest and require the consumer to evaluate subject identity. | Stable, small semantic model and good fit for explaining why a valid predicate about the wrong subject is insufficient. | Apache-2.0; concepts only, no schema or code copied. | **Adapt subject-binding semantics.** |
| [Sigstore root-signing](https://github.com/sigstore/root-signing) and its [keyholder manual](https://github.com/sigstore/root-signing/blob/main/playbooks/tuf-on-ci/SIGNER.md) | Keyholders review the exact proposed change, sign with their own hardware key, and return signatures through a controlled event; staging and client tests precede publication. | Actively operated production trust-root ceremony. Its multi-keyholder and cloud workflow is disproportionate for the lone-human development policy. | Apache-2.0; no code, workflow, service, key, or dependency copied. | **Use as ceremony inspiration, not a dependency.** |

### Build versus adopt

TruePanel continues to adopt the installed OpenSSH verifier, which saves a
custom cryptographic parser and its maintenance burden. The missing control is
application-specific composition: only TruePanel knows that the kit's handoff
fingerprint must equal the independently confirmed enrollment fingerprint
before displaying a signing action. That comparison is therefore implemented
as a small TruePanel-owned interface with deterministic tests.

No third-party code, schema, package, service, credential, key, or dataset was
incorporated. There are no new runtime dependencies or notice-file obligations.

### Rejected paths

- Relying on the later SSHSIG verification: safe final rejection, unsafe human
  instruction timing.
- Matching only `jt-development-review`: a principal label is not a key
  identity.
- Trusting the kit manifest: coordinated kit files can agree about the wrong
  key.
- Embedding the enrollment receipt in the kit as a new trust root: the receipt
  is unsigned and does not authenticate JT.
- Adding TUF, in-toto, or Sigstore runtimes: useful semantics, excessive
  dependency and operational weight for this narrow boundary.
- Reimplementing SSHSIG parsing: unnecessary security-sensitive code when the
  installed OpenSSH verifier already exists.

### Collaboration opportunity

The strongest external conversation is with the Sigstore root-signing and TUF
maintainer communities about how small teams should expose pre-signing subject
and key-identity comparisons without implying threshold trust. No external
contact was made.

## HoloDeck proof

`docs/evidence/aegis-signing-kit-enrollment-binding-v1.json` records seven
scenarios: one exact kit advances only to independent audit, one honest missing
kit names the export action, and five same-principal, reverse-binding,
coordinated-presentation, key-ID, or roster substitutions hold. There are zero
unsafe-ready outcomes, signer invocations, private-key inputs, production
acceptances, deployments, hardware actions, or runtime writes.

Recovery Coverage Matrix status remains **8/8 trusted, 0 gaps**.
