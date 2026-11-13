# AEGIS revocation archive renewal

## Outcome

AEGIS now re-verifies the exact signed CRL and authorized OCSP evidence packages,
requires both packages to describe the same operator, TSA certificate, issuer, and
serial, and binds both predecessor RFC 3161 tokens into a generation-scoped renewal
manifest. A new RFC 3161 timestamp must cover that exact manifest after the predecessor
timestamps and before the earliest of the CRL, OCSP, governed timestamp-authority, or
digest-policy deadlines.

The format deliberately identifies itself as `ERS-INSPIRED-TIMESTAMP-RENEWAL` and sets
`rfc4998_wire_compatible` to false. It adopts the important renewal invariant without
claiming ASN.1 Evidence Record Syntax interoperability. Generation must advance exactly
`N → N+1`; mismatched identities, missing or tampered predecessor tokens, expired
policy, late renewal, token substitution, skipped generations, and authority escalation
all fail closed.

The integration also repaired a time-dependent HoloDeck CRL fixture discovered when
its fixed validity window expired. The fixture now derives its validity window from the
rehearsal clock while preserving deterministic outcomes.

## HoloDeck evidence

Ten isolated paths trust one combined renewal and hold nine identity, custody,
freshness, chronology, generation, or authority failures. The fixture creates a shared
CA/TSA/OCSP-responder identity, a real signed DER CRL, a real signed DER OCSP response,
two predecessor archive timestamps, and one renewal timestamp. Five temporary private
keys are created and none retained.

Recovery coverage remains 8/8. Shared cooling appears at sample 19 versus isolated
thresholds at sample 46: a 27-sample lead at 0.95 evidence-weight confidence.

Evidence: `docs/evidence/aegis-temperature-revocation-archive-renewal-v1.json`

## Prior-Art Field Report

| Candidate | Actual material inspected | Capability, maturity, and fit | Dependency / security / license | Decision |
| --- | --- | --- | --- | --- |
| RFC 4998 ERS | Archive Timestamp Chain/Sequence definitions and Sections 4.2/5 renewal rules | Normative model for timestamp renewal versus hash-tree renewal; directly supplies the predecessor-binding and renew-before-weakness invariants | Standard; no code or attribution obligation | **Adopt semantics, not wire format.** One CRL and one OCSP object do not justify an ASN.1/Merkle implementation yet. |
| RFC 6283 XMLERS | XML evidence-record structure, cryptographic information, timestamp renewal, hash-tree renewal | Equivalent long-term model with explicit CRL/OCSP material, but canonical XML and schema machinery add risk and weight | Standard; no code copied | **Architectural cross-check only.** |
| ETSI DSS | Current documentation and `ASN1EvidenceRecordRenewalDigestBuilder` usage | Mature validation and renewal-digest implementation with strong tests; documentation explicitly says evidence-record creation needs a preservation system outside DSS | Java modules under LGPL-2.1; substantial JVM/XML/CMS surface | **Do not embed.** Use as a behavior oracle and potential interoperability test partner. |
| `fischerf/ervis` | README, license, `evidence_record.py`, renewal and hash-tree methods | Clear educational visualization, but source explicitly concatenates strings instead of cryptographic hashes and uses abstract local timestamps rather than DER/RFC 3161 | MIT; small dependency but security-inappropriate | **Reject for code reuse.** Useful only for explaining ERS concepts. |
| Bouncy Castle ERS | Public implementation issues for reduced-tree mapping and missing renewal operations | Mature crypto project, but the inspected ERS issue history shows unresolved semantic/coverage concerns and Java would still be disproportionate | Bouncy Castle license; large Java dependency | **Defer interoperability testing; do not adopt here.** |
| Sigstore bundles/Cosign | Bundle protobuf/docs and current `VerifyRFC3161Timestamp` code | Excellent portable verification-material container; still leaves CRL/OCSP policy to callers and does not implement evidence-record renewal | Apache-2.0; no code copied | **Collaboration target, not renewal engine.** |
| Existing OpenSSL adapter | Real DER CRL, OCSP, PKIX/EKU, and RFC 3161 verification already exercised by AEGIS | Mature, already installed, fixed-argv, no-shell, and replaceable; avoids another parser or service | Apache-2.0 executable; no added dependency or network | **Reuse behind TruePanel interfaces.** |

Sources inspected 2026-11-11: [RFC 4998](https://datatracker.ietf.org/doc/rfc4998/),
[RFC 6283](https://www.rfc-editor.org/rfc/rfc6283.html),
[ETSI DSS evidence-record documentation](https://ec.europa.eu/digital-building-blocks/DSS/webapp-demo/doc/dss-documentation.html),
[ETSI DSS repository](https://github.com/esig/dss),
[`ervis` source](https://github.com/fischerf/ervis/blob/main/evidence_record.py),
[`ervis` license](https://github.com/fischerf/ervis/blob/main/LICENSE),
[Bouncy Castle ERS issue](https://github.com/bcgit/bc-java/issues/1164),
[Sigstore bundle format](https://github.com/sigstore/docs/blob/main/content/en/about/bundle.md), and
[Cosign timestamp verification](https://github.com/sigstore/cosign/blob/main/pkg/cosign/verify.go).

## Provenance, rejected paths, and risks

No third-party source code, schema, package, service, credential, key, certificate,
revocation object, or dataset was copied. The implementation is new TruePanel code and
continues to wrap the installed OpenSSL executable. No new runtime dependency or notice
file was required.

Rejected: claiming RFC 4998 compatibility without ASN.1 conformance; importing an
educational non-cryptographic implementation; accepting CRL and OCSP objects for
different identities; trusting prior result summaries without re-verification; renewing
only the newest token without binding both predecessors; allowing generation skips;
renewing after the earliest status, TSA, or digest-policy deadline; automatic trust-
bundle activation; and any online TSA or revocation fetch during evaluation.

This proves one timestamp-renewal generation, not hash-algorithm migration, full ERS
interchange, production TSA custody, independent policy monitoring, or durable archive
storage. The strongest next step is cryptographic-agility rehearsal: introduce a second
digest policy and hash-tree-renewal generation that rehashes the original objects plus
the complete prior archive before SHA-256 policy expiry. ETSI DSS maintainers are the
best interoperability collaborators; Sigstore maintainers are the best portable-bundle
collaboration opportunity.
