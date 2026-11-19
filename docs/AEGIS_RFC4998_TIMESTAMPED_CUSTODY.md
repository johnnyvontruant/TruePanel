# AEGIS RFC 4998 timestamped custody

## Outcome

AEGIS now rehearses independent signing-time evidence for the exact SSHSIG that
authenticates custody of a dual-oracle RFC 4998 receipt. A bounded TruePanel
gate accepts only a cryptographically valid RFC 3161 response over the exact
ASCII signature bytes, under an explicit policy OID, digest policy, protected
trust anchor, and the custody event's 15-minute validity window.

The successful result is `RFC3161_CUSTODY_TIME_REHEARSED`. It does not make the
HoloDeck record active, production trusted, deployable, or hardware-authorized.

## Architecture

| Boundary | Contract |
|---|---|
| Authenticated custody | Requires the prior SSHSIG result, exact record identity, both oracle receipts, verified custodian, and every operational authority denied. |
| Countersignature input | Timestamps the exact detached SSHSIG bytes, not merely the record or a caller-supplied signing time. |
| RFC 3161 verifier | Reuses `OpenSslRfc3161TimestampVerifier`, a protected explicit CA bundle, expected policy OID, SHA-256 policy, strict timestamping EKU through OpenSSL, and memory-backed inputs. |
| Time policy | Requires the independently signed `genTime` to fall inside the custody event's signed `issued_at` / `expires_at` window. |
| HoloDeck | Creates ephemeral custodian and TSA keys, one real timestamp response, and ten deterministic outcomes without retaining keys, tokens, or credentials. |
| CI | Runs after authenticated custody, consumes the same-run dual-oracle receipt, byte-compares reviewed evidence, and uploads the timestamped-custody checkride. |

## Scenario evidence

Ten scenarios produce one timestamped rehearsal, one explicit timestamp-required
state, and eight holds. Truncated tokens, an unrelated root, wrong policy,
digest-policy mismatch, signature substitution, timestamps before or after the
custody window, and authority escalation all fail. The Recovery Coverage Matrix
remains 8/8 with zero gaps, and shared-cooling diagnosis remains 27 samples
earlier than isolated thresholds (sample 19 versus 46).

## Prior-Art Field Report

Research was refreshed against upstream specifications, source, tests, release
activity, security advisories, and licensing on 2026-11-18.

| Candidate | What it supplies | Maturity, security, and fit | License / weight | Decision |
|---|---|---|---|---|
| [RFC 3161](https://www.rfc-editor.org/rfc/rfc3161.html) + [OpenSSL `ts`](https://docs.openssl.org/master/man1/openssl-ts/) | Standard proof-of-existence, message-imprint binding, signed `genTime`, TSA policy OID, timestamping-only EKU, and local verification. | Mature, already wrapped by TruePanel, offline, and directly testable. OpenSSL verifies the response against exact bytes and an explicit CA file. | Existing platform dependency; OpenSSL licensing already accepted; no code copied. | **Adopt the existing adapter.** Timestamp exact SSHSIG bytes and enforce the custody window. |
| [Sigstore timestamping](https://docs.sigstore.dev/cosign/verifying/timestamps/) | Explicit recommendation to countersign a signature; signed TSA time for short-lived identities; trusted-root distribution. | Strong conceptual and future interoperability match. The hosted service, TUF roots, bundle protobufs, and network identity are unnecessary for this rehearsal. | Apache-2.0 ecosystem; substantial service and trust-distribution surface. | **Adapt countersigning; defer service adoption.** JT should approach Sigstore when a governed production TSA/root procedure exists. |
| [Sigstore Timestamp Authority](https://github.com/sigstore/timestamp-authority) | Maintained RFC 3161 server, KMS/Tink signing, EKU enforcement, NTP monitoring, and production deployment guidance. | Active and production-oriented, but its documentation notes clock-drift metrics do not stop issuance automatically; operator controls remain essential. | Apache-2.0; server, KMS, monitoring, and operations. | **Do not embed.** Candidate production service after governance, HSM/KMS custody, and fail-closed clock policy are designed. |
| [Notary Project timestamp countersignatures](https://github.com/notaryproject/specifications/blob/main/specs/signature-specification.md) | RFC 3161 countersignatures over the primitive signature plus trust-policy validation. | Mature CNCF-aligned design and close semantic match. Its envelope and X.509 signing scheme would be a larger migration than this SSHSIG boundary requires. | Apache-2.0 specifications/software; OCI-centric dependency surface. | **Adapt the primitive-signature countersignature rule.** Preserve a migration path, add no dependency. |
| [digitorus/timestamp](https://github.com/digitorus/timestamp) | Pure-Go RFC 3161 parsing/creation with focused tests. | Lightweight and BSD-2-Clause, but adopting Go or porting parsing into Python would duplicate the already-hardened OpenSSL verifier. A 2026 advisory in a downstream verifier also illustrates the risk of incomplete timestamping-EKU enforcement. | BSD-2-Clause; new language/runtime or copied parser. | **Reject for this increment.** Keep the replaceable interface and explicit EKU-capable verifier. |
| [Roughtime RFC 10049](https://datatracker.ietf.org/doc/rfc10049/) | Cryptographically attributable rough time and ecosystem misbehavior evidence. | Newly published Experimental RFC; useful for clock synchronization diversity, not a countersignature proving the custody signature existed. | Specification; would add network protocol and server-set operations. | **Architectural inspiration only.** It cannot replace RFC 3161 proof-of-existence. |

### Build-versus-adopt conclusion

The verified shortcut is the existing OpenSSL RFC 3161 adapter. TruePanel adds
only the narrow composition policy: prior custody must be authenticated, the
timestamp covers the exact SSHSIG, its policy and digest must match, and its
signed time must fall inside the custody window. No external code, schema,
service, trust root, certificate, credential, key, or runtime package was added.

The strongest collaboration opportunity is Sigstore's Timestamp Authority and
Notary Project maintainers. JT should ask how best to package an SSHSIG
countersignature and offline root material in a standard portable bundle once
production custodian and TSA governance exist.

## Failed and deferred approaches

- Timestamping the record statement rather than the primitive signature was
  rejected because it proves record existence, not when this custodian signed.
- Signer-provided `issued_at` remains policy context, never independent time.
- Public TSA calls were rejected: they add network dependency and unapproved
  trust roots, and would publish a digest derived from internal evidence.
- Reusable fixture keys/tokens were rejected. HoloDeck preserves outcomes only.
- Sigstore, Notation, and a new RFC 3161 parsing library were not adopted because
  they add envelope, service, or dependency weight without strengthening this
  existing offline verifier.

## Reproduction

```text
pytest -q tests/test_aegis_rfc4998_timestamped_custody.py tests/test_aegis_rfc4998_authenticated_custody.py
python -m truepanel.holodeck.aegis_rfc4998_timestamped_custody --output /tmp/aegis-timestamped-custody.json
python -m truepanel.hangar validate --root .
node --check truepanel/web/static/reliability-view.js
```

## Remaining gate

Provision governed custodian and TSA identities with protected keys, explicit
policy and root rotation, fail-closed clock monitoring, preserved revocation
evidence, and a fresh passive Black Box EvidenceRecord with fresh dual-oracle
receipts. Until that live-but-read-only checkride exists, active custody time and
production trust remain `PENDING`.
