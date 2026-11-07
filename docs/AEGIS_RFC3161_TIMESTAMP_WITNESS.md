# AEGIS RFC 3161 timestamp witness

## Outcome

AEGIS can now require an independently signed timestamp over the exact reviewer SSHSIG
bytes before a historical review is eligible for quorum. The TruePanel-owned adapter
uses the installed OpenSSL RFC 3161 verifier with a protected trust-anchor snapshot,
an exact policy OID, SHA-256, bounded input, fixed executable path, timeout, and
memory-backed temporary inputs.

The timestamp must be no earlier than the signed review statement, no more than 15
minutes later, no later than the evaluation time, and strictly before a matching
dual-root-governed compromise time. Timestamp validity never grants field validation,
candidate acceptance, installation, deployment, runtime, storage, network, or hardware
authority.

## HoloDeck evidence

The seven-scenario checkride creates an isolated two-level timestamp PKI and issues
real DER RFC 3161 tokens over fixture SSHSIG files. It accepts one witnessed
pre-compromise signature and one unaffected reviewer. It holds a post-compromise
timestamp, tampered token, timestamp delayed beyond 15 minutes, untrusted root
transition, and authority-escalated review. Five temporary private keys are created and
none are retained.

The Recovery Coverage Matrix remains 8/8 trusted. The fan-degradation reference still
correlates shared cooling at sample 19 versus isolated thresholds at sample 46, a
27-sample lead at 0.95 evidence-weight confidence. Every operational action counter is
zero.

Evidence: `docs/evidence/aegis-temperature-reviewer-timestamp-witness-v1.json`

## Prior-Art Field Report

| Candidate | Actual capability inspected | Maturity, fit, and security | License / obligations | Recommendation |
| --- | --- | --- | --- | --- |
| RFC 3161 | Standardizes a signed timestamp token, message imprint, TSA identity, policy, nonce, and historical signature/revocation verification | Stable PKIX standard and exact semantic fit; TSA operational policy remains outside the standard | IETF standard; cite the RFC, no code copied | **Adopt the wire semantics and verification rules.** |
| OpenSSL `ts` | Creates and verifies RFC 3161 queries/responses, certificate chains, message imprints, and policy identifiers | Mature, already available in the development platform, small integration surface; subprocess and system-version behavior must remain isolated | Apache-2.0; invoked as an installed executable, no source copied or redistributed | **Adopt behind the TruePanel interface.** Keep optional until TrueNAS packaging is explicitly guaranteed. |
| Sigstore timestamps and bundles | Countersigns signatures with RFC 3161 tokens and stores zero or more timestamps in the verification bundle | Production model and strongest interoperability path; full Fulcio/Rekor/Cosign adoption adds network, identity, registry, and monitoring dependencies | Apache-2.0 ecosystem; concepts only | **Adapt countersigning and bundle ideas**, not the control plane. |
| Rekor v1 integrated time | Signed log-entry time can witness existence | Mature but its documented clock is not externally verifiable and v1 time is mutable outside the append-only node | Apache-2.0 ecosystem; no code copied | **Reject as the sole time source.** |
| Rekor v2 plus TSA | Separates the signed timestamp authority from the transparency log | Promising defense in depth and future collaboration target; currently unnecessary for offline deterministic fixtures | Apache-2.0 ecosystem; no code copied | **Evaluate later** as a monitored second witness. |
| A signer-authenticated `prepared_at_utc` | Preserves claimed chronology inside the signed review | Dependency-free but controlled by the potentially compromised signer | Original TruePanel field | **Retain only as a consistency bound, never as the trust source.** |

Sources inspected on 2026-11-06: [RFC 3161](https://datatracker.ietf.org/doc/html/rfc3161), [OpenSSL `ts` documentation](https://docs.openssl.org/master/man1/openssl-ts/), [OpenSSL timestamp verification API](https://docs.openssl.org/3.5/man3/TS_VERIFY_CTX/), [OpenSSL `ts` source](https://github.com/openssl/openssl/blob/master/apps/ts.c), [Sigstore timestamp guidance](https://docs.sigstore.dev/cosign/verifying/timestamps/), and [Sigstore bundle format](https://docs.sigstore.dev/about/bundle/).

## Incorporated shortcut and provenance

No external source code, Python package, service, credential, production key, network
call, or vendor schema was copied into TruePanel. Original code invokes the installed
Apache-2.0 OpenSSL command through `OpenSslRfc3161TimestampVerifier`. The rest of AEGIS
depends only on the TruePanel-owned callable interface, so another standards-compliant
verifier can replace it.

The implementation deliberately does not query a public TSA. HoloDeck generates a
temporary root and TSA certificate, issues real tokens locally, deletes all private
material with the temporary directory, and preserves only the result summary.

## Rejected paths and limitations

- Trusting `prepared_at_utc`: it is authenticated but signer-controlled.
- Timestamping the review artifact rather than its signature: countersigning the exact
  SSHSIG more directly bounds signature creation.
- Adding public TSA HTTP calls: this would introduce availability, privacy, egress,
  provider-policy, credential, and retention questions.
- Adopting all of Sigstore: Fulcio, Rekor, OCI, OIDC, and Kubernetes assumptions are
  disproportionate for this offline evidence boundary.
- Treating one TSA as absolute time: its clock and custody remain trust assumptions.

This prototype validates the token and current certificate chain but does not yet
preserve historical CRLs/OCSP responses, rotate TSA trust roots, require multiple
independent TSAs, or monitor a transparency log. It proves protocol enforcement, not a
production TSA's clock quality or custody.

The strongest collaboration opportunity is a review with Sigstore timestamp and trust-
root maintainers, focused on bundle compatibility, multi-TSA thresholds, trust-root
rotation, and long-term revocation evidence.

## Strongest next step

Define the governed timestamp trust-root bundle and archival revocation policy: exact
allowed TSA operators, validity intervals, rotation, CRL/OCSP preservation, maximum
witness delay, and whether an independently monitored transparency proof is mandatory
alongside RFC 3161. Continue to stop before network acquisition or production use.
