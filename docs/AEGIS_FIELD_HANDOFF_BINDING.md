# AEGIS final-consumer handoff binding

Reviewed 2026-10-05 against the pinned upstream revisions linked below.

## Finding

The release-bound verifier confirmation handoff was audited before the field
ceremony, but the ceremony itself accepted the nested receipt as a mapping. A
caller could therefore skip the handoff file-set, manifest, comparison-kit, and
release-binding checks while still reaching the public-roster gate. The receipt
was valid evidence, but it did not prove that the final consumer had enforced
the complete evidence chain.

The final consumer now accepts only the handoff directory, comparison-kit
directory, pinned verifier receipt and source, and observation time. It calls
the same TruePanel-owned handoff auditor itself and uses the nested receipt only
after that audit succeeds. The raw-receipt API and CLI paths are removed.

## Prior-art field report

| Candidate | Actual code or specification inspected | Useful lesson | Maturity, fit, and security | License / obligations | Decision and likely time saved |
|---|---|---|---|---|---|
| [in-toto verification](https://github.com/in-toto/in-toto/blob/e352b43ad7cb8915d84c36d791aa61346152a0a3/in_toto/verifylib.py) | `verifylib.py` verifies layout expiry, metadata signatures, step thresholds, and material/product rules at the verifier rather than trusting a caller's summary. Latest inspected commit was 2026-08-27 and the repository includes extensive verification tests. | The terminal consumer must verify the ordered evidence chain it relies on. | Mature, maintained, strong conceptual fit; adopting its full layout/runtime would add dependencies and a much broader policy surface than this development-only ceremony needs. | Apache-2.0; preserve license, notices, and changed-file markings if code is copied. | Adapt the consumer-side chain rule, not code. Avoids designing the composition rule from scratch while adding zero dependency weight. |
| [Sigstore Python verifier](https://github.com/sigstore/sigstore-python/blob/1e577308505068552fc808027181e2ed4a947654/sigstore/verify/verifier.py) | The verifier establishes trusted time from bundle material, rejects excessive or duplicate timestamps, and validates certificates at that time under a trusted root. Latest inspected commit was 2026-10-04; unit tests exercise bundle verification. | A bundle is only useful when the final verifier validates its verification material and time context. | Highly active and security-focused, but its certificate, transparency-log, TUF, and network trust model is far heavier than an offline SSHSIG development handoff. | Apache-2.0; preserve license and notices for redistributed code. | Architectural inspiration only. Full adoption would increase attack surface and operational complexity rather than save verified development time here. |
| [python-tuf Updater](https://github.com/theupdateframework/python-tuf/blob/1db152642ec023448a9dde7f199ddd63e920a108/tuf/ngclient/updater.py) | `Updater` loads a trusted root, refreshes root → timestamp → snapshot → targets in order, and verifies downloaded targets against metadata. Latest inspected commit was 2026-09-29 and the project has broad updater regression coverage. | Start from an explicit trust anchor and re-run ordered transition checks at the consuming client. | Mature and maintained with excellent fail-closed semantics; network/download and metadata-role machinery do not fit this local two-file handoff. | Apache-2.0 in the inspected repository; source headers also identify MIT OR Apache-2.0 for individual files. Preserve the applicable license and notices if copied. | Adapt the final-client revalidation pattern. Do not add the package for a local, dependency-free ceremony. |
| [SLSA VSA](https://github.com/slsa-framework/slsa/blob/82b296d49e4c8301e7db565f23620ffe89092a0c/spec/verification_summary.md) | The specification binds subject, verifier, verification time, policy, and all input-attestation digests; its verification guidance requires subject matching. Latest inspected commit was 2026-09-29. | A summary cannot stand in for its inputs unless the verifier identity, policy, subject, and input evidence are bound and trusted. | Current, ecosystem-aligned specification; useful vocabulary, but its parsing rule permits unknown fields while this narrow safety boundary deliberately fails closed on extensions. | Community Specification License 1.0; license file identifies CC-BY-4.0 for the license text. Attribution is required for copied specification text. | Adapt subject/input binding semantics only. No schema or text copied into runtime. |

All four candidates are actively maintained at the inspected revisions and have
clear licenses. None provides a smaller or safer drop-in than calling the
existing TruePanel handoff auditor from the final consumer. No third-party code,
schema, package, service, key, credential, or dataset was incorporated.

## Build versus adopt

Build the small TruePanel-owned composition adapter and keep the upstream ideas
as testable invariants. Adopting in-toto or Sigstore would save little code here
while importing cryptographic policy and dependency lifecycle that TruePanel
does not need. python-tuf solves a different network update problem. SLSA VSA is
an interoperability format, not an enforcement engine.

The strongest future collaboration opportunity is the in-toto maintainer
community: TruePanel's sequence of public evidence, independent witness, and
final-consumer reconstruction maps most directly to its step/link verification
model. JT could ask whether an intentionally small offline layout profile exists
for appliance-development ceremonies before TruePanel invents a broader schema.

## Rejected and failed paths

- **Trust the nested receipt because an earlier caller audited it.** Rejected:
  function arguments do not carry proof that the caller executed the audit.
- **Add a boolean such as `handoff_verified=True`.** Rejected: a caller can set
  it without supplying the evidence.
- **Keep the raw-receipt CLI as a compatibility escape hatch.** Rejected: it
  preserves the exact bypass the increment is meant to close.
- **Adopt a heavyweight attestation runtime now.** Rejected: it expands the
  trust base without solving operator identity or independent delivery.
- **Treat the unsigned manifest as JT authentication.** Rejected: it binds
  public files but cannot authenticate the operator or transport channel.

## Result and remaining boundary

HoloDeck proves one exact handoff reaches only
`ACTION_REQUIRED_PUBLIC_ROSTER`, one raw-receipt bypass is structurally denied,
and seven incomplete, substituted, drifted, extended, or expired inputs hold.
The accepted Recovery Coverage Matrix remains 8/8 trusted with zero gaps.

This increment does not authenticate JT, create or accept a private key, invoke
a signer, provision the real public roster, install software, or grant
production, deployment, hardware, storage, network, or automatic-promotion
authority. The first real ceremony still requires JT's independently compared
digest and protected development-only public roster.
