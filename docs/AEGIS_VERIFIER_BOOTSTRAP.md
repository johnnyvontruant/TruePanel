# AEGIS verifier bootstrap and prior-art field report

## Outcome

The standalone signing-kit auditor now has a canonical public release receipt
that pins its exact reviewed predecessor source at commit
`6bbda7b85142451562eb420f612478b311e6e8eb` using both SHA-256 byte identity and
Git blob identity. The bootstrap verifier checks both identifiers, byte length,
strict receipt shape, absolute regular-file custody, Python syntax, and an exact
standard-library import boundary without executing the auditor.

Success is deliberately named `VERIFIER_CONTENT_PIN_VERIFIED`. It does **not**
claim that the receipt arrived independently, make a kit ready for signature,
accept a private key, invoke a signer, or grant production authority. JT must
obtain the fingerprint through a channel independent of the candidate kit
before relying on the implementation-diversity claim.

## Pinned release

| Property | Value |
|---|---|
| Immutable source | [auditor at `6bbda7b`](https://github.com/johnnyvontruant/TruePanel/blob/6bbda7b85142451562eb420f612478b311e6e8eb/truepanel/holodeck/aegis_independent_kit_auditor.py) |
| SHA-256 | `53852580f448fcb62db18657d64885df5873ea0a4c1a421e23ec2a61f75273be` |
| Git blob SHA-1 | `0b0551a26f0d51e3e3ccf767f017abe26ad6e8c1` |
| Size | 11,252 bytes |
| Runtime | Python 3.11+ standard library, isolated mode |
| Network | Not required |
| TruePanel imports | 0 |
| Private-key inputs | 0 |
| Signer invocations | 0 |

The Git blob identifier is computed over Git's `blob <length>\0<content>` object
representation. It is a repository identity cross-check, not a second modern
cryptographic trust root; SHA-256 remains the byte-integrity pin.

## Safe operator sequence

1. Obtain the receipt or its SHA-256 fingerprint through a JT-controlled channel
   that is independent of the signing kit.
2. Fetch the verifier only from the immutable commit URL shown above.
3. Run the bootstrap check with absolute paths. A success still reports that the
   independent channel is outside TruePanel's proof.
4. Run the pinned verifier with `python -I` against the public signing kit and
   preserve its canonical witness outside the kit.
5. Require the internal and independent audits to agree before considering an
   offline *development-only* signature.

## HoloDeck proof

The preserved checkride contains 15 scenarios: one exact content pin and 14
`HOLD` results for source, SHA-256, Git blob, byte-length, commit, source URL,
authority, schema-extension, canonicalization, symlink, network-import,
TruePanel-import, and private-key-input changes. It records zero verifier
executions during pin checking, unsafe-ready results, manufactured independent
channels, private-key inputs, signer invocations, production acceptances,
deployments, hardware actions, or runtime writes.

Recovery Coverage Matrix v1 remains unchanged at **8/8 trusted, 0 gaps**. This
increment strengthens the review path around the matrix; it does not accept a
new matrix or alter runtime recovery behavior.

## Prior-art field report

| Candidate | What the actual docs/code supply | Fit and maintenance signal | License / obligation | Decision |
|---|---|---|---|---|
| [TUF specification](https://theupdateframework.github.io/specification/) | Explicitly assumes an initial trusted root obtained out of band and separates root trust from target metadata. | Mature cross-ecosystem architecture and the clearest model for the remaining bootstrap boundary. | Specification text is CC-BY 4.0; implementations vary. Attribution required if text is reused. | **Adapt concept.** Keep `independent_channel_verified: false`; do not add TUF runtime weight for one file. |
| [Git `hash-object`](https://git-scm.com/docs/git-hash-object) and [object format](https://git-scm.com/docs/gitformat-loose) | Defines content-addressed blob identity and the exact type/length prefix. | Already present in the development workflow and easy to reproduce independently. | Git is GPL-2.0; using its documented object format or executable adds no copied code to TruePanel. | **Adopt format semantics.** Pair the SHA-1 object ID with SHA-256; never treat SHA-1 alone as sufficient. |
| [Sigstore offline bundles](https://docs.sigstore.dev/cosign/verifying/verify/) | Bundles signatures, timestamps, attestations, and log evidence for offline verification; trusted roots are managed separately. | Active, high-maturity supply-chain ecosystem, but substantially heavier than the current single-file development gate. | Cosign is Apache-2.0; notices would be required if code were redistributed. | **Defer adoption.** Valuable when TruePanel needs transparency-log or identity-backed releases. |
| [Minisign](https://github.com/jedisct1/minisign) | Minimal Ed25519 detached signatures and direct public-key verification. Source confirms a deliberately small verifier surface. | Mature and portable; would add another key format and native dependency beside existing OpenSSH SSHSIG. | ISC; preserve copyright and permission notice if code is copied or redistributed. | **Idea only.** Existing OpenSSH already supplies the required signature primitive. |

No third-party source, schema, package, service, credential, key, or dataset was
copied. TruePanel's verifier and receipt are owned interfaces using standard
library hashing and parsing. The strongest prospective collaboration is with
TUF and Reproducible Builds maintainers on human-usable bootstrap ceremonies
for very small teams.

## Rejected and failed approaches

- **Ship the checksum beside the verifier and call it independent.** This proves
  consistency within one channel, not independent provenance.
- **Use only the Git SHA-1 blob name.** Useful repository identity, insufficient
  as the sole security digest.
- **Execute the verifier while deciding whether it is trusted.** That inverts
  the bootstrap boundary; this check performs parsing and hashing only.
- **Adopt Sigstore, TUF, or Minisign wholesale.** Each can solve a larger release
  problem, but currently adds services, roots, dependencies, or a second key
  system without closing the human out-of-band step.
- **Mint or store JT's signing key.** Explicitly out of scope and structurally
  absent.

## Open risk and next gate

The release receipt and verifier are still published from the same repository
identity. Content is pinned, but organizational/channel independence is not.
The next gate is for JT to preserve the SHA-256 fingerprint through a separate
operator-controlled channel, then provision only the development public-key
roster and dual-audit one real reviewed kit. No signature, deployment, hardware
action, or production acceptance is authorized by this work.
