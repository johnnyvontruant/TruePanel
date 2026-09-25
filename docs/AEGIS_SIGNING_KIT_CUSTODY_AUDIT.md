# AEGIS signing-kit custody audit and prior-art field report

## Result

The public-only development signing kit now includes a deterministic review
card and an offline `audit` command. The card exposes the exact commit, Git
tree, operator-confirmed UTC, public-key fingerprint, receipt digest,
application namespace, development-only scope, and five explicit NO-authority
fields. It is always regenerated from the canonical signing-session JSON; it
is never treated as an independent source of truth.

The audit accepts exactly four pre-signing files. It rejects missing, extra,
symlinked, special, changing, oversized, noncanonical, or substituted content.
It independently rebuilds the manifest, instructions, and review card from the
session and compares their exact bytes and digests. A coordinated change to the
card and its manifest still fails because the manifest is not its own trust
root. A preexisting signature also fails the pre-sign audit so the operator
cannot accidentally bless an unreviewed or replayed directory.

The canonical JSON session remains the only signed object. The card says this
explicitly. Returned-signature verification still reconstructs the clean
checkout, clock witness, handoff, evidence, policy, and receipt before reaching
only `ELIGIBLE_FOR_DEVELOPMENT_CANDIDATE_REVIEW`.

## Operator sequence

1. Export from the exact clean candidate checkout with JT-confirmed UTC.
2. Move only the four-file public kit to the operator-owned signing computer.
3. Run `python -m truepanel.aegis.signing_tool audit --kit <ABSOLUTE_KIT_PATH>`.
4. Compare the review card with the intended commit, tree, time, fingerprint,
   scope, and NO-authority fields.
5. Sign only `aegis-development-signing-session.json` with the shown SSHSIG
   namespace and JT's external private key.
6. Return only the detached `.sig`; verify it from the pinned checkout.

TruePanel still has no signer API and never accepts a private-key path.

## Prior-art comparison

| Candidate | Actual code/spec inspected and transferable lesson | Maturity, test quality, platform fit, dependency/security posture | License / attribution | Build-versus-adopt and verified time saving |
| --- | --- | --- | --- | --- |
| [DSSE protocol](https://github.com/secure-systems-lab/dsse/blob/master/protocol.md) | Signs an unambiguous payload type plus exact serialized bytes. Its verifier requirement that the bytes passed to the application be the same bytes that were verified directly exposes the presentation-substitution hazard. | Focused, stable protocol with reference vectors. Adding an envelope runtime would duplicate the already deployed SSHSIG boundary, but its verified-byte handoff rule fits exactly. | Apache-2.0. No code or schema copied; the report links the source. | **Adapt the invariant, not the package.** The audit parses once, enforces canonical bytes, and derives the card from that object. Saves several design/review days. |
| [TUF specification](https://github.com/theupdateframework/specification/blob/master/tuf-spec.md) | Versioned metadata, expiry, client recomputation of key IDs, and hash/length-bound target metadata show why transported claims must be checked against independently trusted rules. | Highly mature update-security architecture with extensive implementations. Full TUF metadata roles are too heavy for one offline development signature. | Specification repository terms must be reviewed before copying; no text, code, or schema was incorporated. | **Architectural inspiration.** Strict versioned manifest and fail-closed unknown fields; do not add a TUF runtime. Saves policy design time, not implementation code. |
| [Sigstore Bundle protobuf](https://github.com/sigstore/protobuf-specs/blob/main/protos/sigstore_bundle.proto) | Carries a versioned media type, signature content, verification material, transparency/timestamp evidence, and exact key-hint consistency rules in one portable bundle. | Actively maintained, strongly tested ecosystem. Its certificates, transparency log, protobufs, and online identity model outweigh this private NAS-development ceremony. | Apache-2.0. No protobuf or dependency copied. | **Reject runtime adoption; retain bundle separation as a future seam.** Potentially saves weeks for public release verification, but adds negative value here. |
| [Minisign](https://github.com/jedisct1/minisign) | A verified trusted comment is a compact precedent for binding operator-readable metadata rather than placing unauthenticated text beside a signature. | Mature, small, portable, and compatible with Signify. It would introduce a second key format and signer tool despite OpenSSH already being installed. | ISC; attribution required if code is copied. None was copied. | **Compatible fallback, not adopted.** Reconsider on OpenSSH-poor platforms; approximately one week saved there. |
| [OpenSSH SSHSIG](https://github.com/openssh/openssh-portable/blob/master/PROTOCOL.sshsig) | Existing exact-byte detached signature, mandatory application namespace, and allowed-signers verification remain the best cryptographic fit. | Mature platform executable with a substantive [negative regression suite](https://github.com/openssh/openssh-portable/blob/master/regress/sshsig.sh). Zero new Python crypto dependency and no network service. | BSD-style OpenSSH license family. Invoked as an installed executable behind a TruePanel-owned adapter. | **Continue adopted interface.** Avoids custom crypto, key parsing, and signature-envelope work—several weeks of high-risk development. |

## Recommendation and provenance

Keep the TruePanel-owned canonical session, deterministic renderer, strict
manifest, and offline audit. Continue using the installed OpenSSH verifier and
external signer protocol. Do not add DSSE, Sigstore, TUF, or Minisign as a
runtime dependency for this narrow development-only boundary. DSSE/Sigstore
maintainers are the strongest prospective collaboration target for advice on
verified-payload-to-presentation handoff and portable offline bundles; no one
was contacted.

No external code, schema, package, service, credential, key, or dataset was
copied or added. Only architecture and security invariants were adapted, with
links and licensing notes preserved above.

## Failed paths and challenged assumptions

- A digest in a manifest does not authenticate the manifest. The audit
  reconstructs the complete expected manifest from the canonical session.
- A review card shipped beside signed data is not automatically covered by the
  signature. The audit regenerates it, and the card plainly says the JSON is
  the signed object.
- Valid JSON is not necessarily the byte sequence JT will sign. Pretty-printed,
  reordered, duplicated, or otherwise noncanonical session bytes fail.
- Letting an existing `.sig` coexist during pre-sign audit blurs review and
  verification phases. The exact pre-sign file set excludes it.
- Hashing only the card permits coordinated card-and-manifest substitution.
  The expected card and hash are derived independently from the session.

## Evidence and remaining risk

The HoloDeck custody checkride has 12 scenarios: one exact kit reaches
`READY_FOR_OPERATOR_SIGNATURE`, one externally signed disposable fixture
reaches development-review eligibility, and ten attacks produce `HOLD`.
Accepted review-card substitutions, unsafe-ready outcomes, private-key inputs,
TruePanel signer invocations, production acceptances, deployments, hardware
actions, and runtime writes are zero. The Recovery Coverage Matrix remains
8/8 trusted with zero gaps.

This proves deterministic presentation integrity in simulation, not JT's
identity or a real field ceremony. A compromised binary could lie about both
the session and card; the signing computer therefore needs a pinned reviewed
TruePanel build or independently checked source. JT's real public roster and
signature remain external and unprovisioned.
