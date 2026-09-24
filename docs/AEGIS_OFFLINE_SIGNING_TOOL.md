# AEGIS public-only offline signing tool and prior-art field report

## Result

TruePanel can now export the exact content-bound development signing session as
a three-file, public-only kit outside the source checkout and verify the
returned detached signature without ever accepting a private-key path or
invoking a signer. The export requires an explicit JT-confirmed UTC value,
reconstructs the clean commit and tree, and writes only exclusive `0600` files
inside a `0700` directory. Existing output, symlinks, special files, oversized
inputs, partial writes, checkout drift, evidence drift, authority escalation,
and invalid signatures fail closed.

The kit contains the canonical session, a digest and authority manifest, and
operator instructions. The manifest states that production, deployment,
hardware, storage-write, and automatic-promotion authority are false. The
verification result can reach only
`ELIGIBLE_FOR_DEVELOPMENT_CANDIDATE_REVIEW`; it cannot accept a candidate,
install an AIRWORTHINESS envelope, promote a stage, deploy, or control hardware.

Mission Control keeps the development review visible on phones and now names
the actual ceremony: export public kit, sign offline with the operator-owned
key, and verify the returned signature. It explicitly says that TruePanel never
handles the private key.

## Operator field sequence

1. Prepare a separately reviewed `truepanel.aegis-development-signing-materials/v1`
   bundle and protected `jt-development-review` public roster.
2. From the exact clean candidate checkout, compare UTC and run
   `python -m truepanel.aegis.signing_tool export` with `--confirm-utc`.
3. Move only the exported public kit to JT's operator-owned signing computer.
4. Inspect its commit, tree, UTC, scope, fingerprint, digest, and all five
   NO-authority fields; sign the canonical session with `ssh-keygen -Y sign`.
5. Return only the `.sig` file and run the tool's `verify` command against the
   same pinned checkout and public roster.

This increment deliberately does not create JT's key, public roster, real
materials bundle, or signature. Those are operator-owned field inputs, not
fixtures TruePanel may fabricate.

## Prior-art comparison

| Candidate | Capability and actual material inspected | Maturity, test quality, fit, and dependency weight | Security and licensing | Decision / likely time saved |
| --- | --- | --- | --- | --- |
| [OpenSSH SSHSIG protocol](https://github.com/openssh/openssh-portable/blob/master/PROTOCOL.sshsig) and [regression suite](https://github.com/openssh/openssh-portable/blob/master/regress/sshsig.sh) | Detached armored signatures, mandatory non-empty application namespace, signed message hash, principal/key roster, and negative cases for wrong content, key, principal, namespace, and signer options. | Mature, actively exercised portable implementation; `ssh-keygen` is already present and its regression coverage directly matches the ceremony. Zero new Python package or crypto parser. | BSD-style family of licenses. TruePanel invokes the installed verifier and copies no source. Fixed namespace prevents cross-purpose reuse; the private signer remains outside TruePanel. | **Adopted behind a TruePanel-owned interface.** Avoids implementing and auditing signature parsing, key formats, and crypto—several weeks of risky work. |
| [Minisign](https://github.com/jedisct1/minisign) and [ISC license](https://github.com/jedisct1/minisign/blob/master/LICENSE) | Small cross-platform Ed25519 file signing, password-protected secret keys, public-key verification, and Signify compatibility. The project now recommends its Zig implementation for new features. | Focused and lightweight with attractive operator ergonomics, but adds a binary, a second key format, and a parallel trust roster solely for this path. | ISC-compatible and security-oriented; no credential-harvesting concern found. A second secret-key tool increases operational surface without adding needed scope separation. | **Compatible but rejected for now.** Reconsider for platforms without OpenSSH; likely one week saved there, negative value on current TruePanel hosts. |
| [Sigstore Cosign](https://github.com/sigstore/cosign) and [cross-platform/KMS/registry tests](https://github.com/sigstore/cosign/blob/main/.github/workflows/e2e-tests.yml) | Keyless OIDC/Fulcio/Rekor, hardware/KMS keys, bring-your-own PKI, OCI storage, digest-bound detached payloads, and broad end-to-end testing. | Highly mature and actively maintained, but its OCI, identity, transparency-log, KMS, and network model is far broader than one offline NAS-development signature. | Apache-2.0. Default keyless signing can publish identity information to a permanent public log; that is inappropriate as an implicit choice for this private ceremony. | **Architectural inspiration, not dependency.** Revisit for release artifacts or transparency, after privacy and online-service review. |
| [in-toto](https://github.com/in-toto/in-toto) | Signed layouts name authorized functionaries; links record materials/products; verification chains evidence and rejects unplanned artifacts. The inspected documentation recommends a terminal `DISALLOW *` rule. | Mature supply-chain framework with substantive tests and package-manager use, but a full layout runtime and schema would duplicate TruePanel's narrower content-bound session. | Apache-2.0. Strong fail-closed semantics; adding it now would increase package and policy surface. | **Adapt the evidence-chain and explicit-denial ideas.** Do not copy code or schema; likely saves design time, not runtime code. |
| [SLSA provenance v1.2](https://slsa.dev/spec/v1.2/provenance) and [TUF](https://theupdateframework.github.io/specification/latest/) | Authenticated subjects/parameters and scoped, expiring offline trust roles. | Strong standards with broad ecosystems; full adoption is wider than this one-person development boundary. | Open specifications with compatible conceptual use. | **Architectural guidance.** Keep the adapter replaceable so future attestations or threshold production roles can coexist. |

## Build-versus-adopt conclusion

Adopt OpenSSH's installed verifier and external signer protocol, while keeping
the export, evidence reconstruction, strict schemas, authority manifest, and
consumer boundaries in TruePanel. This is the smallest dependency surface and
the clearest replacement seam. Minisign is the best fallback for a future
OpenSSH-poor platform. Cosign is the strongest future collaboration target for
release transparency, while OpenSSH portable maintainers are the most relevant
technical contact for SSHSIG and allowed-signers edge cases. No maintainer was
contacted.

No external code, schema, library, service, credential, key, or dataset was
copied or added. Provenance is preserved by the links above and by the existing
OpenSSH adapter boundary.

## Failed approaches and challenged assumptions

- Writing directly into the final export directory could leave a misleading
  partial kit after an I/O error. The implementation now removes only its fixed
  exclusive files and leaves any unexpectedly occupied directory fail closed.
- A single `os.write` is not guaranteed to write every byte. The exporter now
  loops until all bytes are persisted and fsyncs files and the directory.
- A valid signature does not make a changed checkout valid. Verification
  reconstructs the session and holds after post-export source drift.
- A convenient signing wrapper would pull the private-key path into TruePanel's
  input surface. The tool intentionally prints an external OpenSSH command and
  contains no signer API.
- A manifest alone is not verification evidence. The verifier ignores claims
  in the presentation manifest and reconstructs the canonical session from the
  authoritative inputs.

## HoloDeck proof and remaining risk

The preserved checkride has ten scenarios: one public export ready, one real
disposable SSHSIG eligible for development review, and eight HOLD results.
It covers absent UTC confirmation, output inside the checkout, symlinked and
pre-signed materials, occupied output, session authority tampering, an invalid
signature, and source drift after export. Unsafe-ready outcomes, private keys
accepted by TruePanel, TruePanel signer invocations, production acceptances,
deployments, hardware actions, and runtime writes are all zero. Recovery
Coverage Matrix remains 8/8 trusted with zero gaps.

The remaining gate is human and intentionally external: JT must provision the
protected development public roster and create one real offline signature over
a freshly reviewed materials bundle. Until then, the tool is proven with a
disposable HoloDeck identity only and grants no acceptance or operational
authority.
