# AEGIS governed timestamp trust

## Outcome

AEGIS now separates cryptographic RFC 3161 verification from authority governance. A
timestamp can count only when its root fingerprint, policy OID, issuance time, and
operator match an active authority in an unexpired generation. At least two distinct
operators are required; multiple tokens from one operator count once.

The gate grants reviewer-quorum eligibility only. It cannot validate, install, deploy,
capture, mutate, write storage or networking, or actuate hardware.

## HoloDeck evidence

Seven deterministic paths trust one two-operator threshold and hold duplicate-operator
tokens, an expired bundle, an unknown root, policy drift, authority escalation, and a
bundle that lists one operator twice. Recovery coverage remains 8/8. Shared cooling is
identified at sample 19 versus isolated thresholds at sample 46, a 27-sample lead at
0.95 evidence-weight confidence. All operational counters remain zero.

Evidence: `docs/evidence/aegis-temperature-timestamp-trust-bundle-v1.json`

## Prior-Art Field Report

| Candidate | What it supplies | Fit / maturity / security | License | Decision |
| --- | --- | --- | --- | --- |
| Sigstore TrustedRoot | TSA operator identity, validity intervals, historical authorities, and distinct-operator threshold semantics | Strongest direct fit and actively maintained; full Sigstore control plane is unnecessary | Apache-2.0; concepts only | **Adapt the trust semantics.** |
| RFC 3161 | Signed time, policy OID, imprint binding, nonce and revocation guidance | Stable standard; deliberately leaves TSA operational trust to relying parties | IETF standard | **Retain as token protocol.** |
| RFC 6024 | Application-scoped trust anchors and constraints | Useful warning against sharing general system roots | IETF standard | **Use a dedicated AEGIS trust bundle.** |
| TUF root metadata | Versions, expiry, threshold keys and consecutive rotation | Mature and excellent future signing model; not a timestamp verifier | Specification; reference implementations have permissive licenses | **Adapt generation/expiry; add signing next.** |
| OpenSSL trust stores | Multiple anchors, policy and CRL verification controls | Already present and isolated behind TruePanel's adapter | Apache-2.0 executable | **Reuse; do not duplicate PKIX.** |

Sources inspected 2026-11-07: [RFC 3161](https://www.rfc-editor.org/rfc/rfc3161.html),
[RFC 6024](https://www.rfc-editor.org/info/rfc6024),
[Sigstore trust-root schema](https://github.com/sigstore/protobuf-specs/blob/main/protos/sigstore_trustroot.proto),
[Sigstore timestamp guidance](https://docs.sigstore.dev/cosign/verifying/timestamps/),
[TUF specification](https://github.com/theupdateframework/specification/blob/master/tuf-spec.md), and
[OpenSSL timestamp verification](https://docs.openssl.org/master/man1/openssl-ts/).

## Provenance and rejected paths

No third-party source, package, schema, service, credential, key, or dataset was copied.
The original TruePanel policy consumes results from the replaceable RFC 3161 verifier.
It does not query public TSAs or introduce Fulcio, Rekor, OCI, OIDC, Kubernetes, or a
network dependency.

Rejected: counting tokens rather than operators; trusting the system-wide CA store;
accepting future or expired authority intervals; silently accepting unknown policy OIDs;
and treating two certificates owned by one operator as independent.

## Open risks and next step

The bundle is not yet signed, generation continuity is not yet externally authenticated,
and historical CRL/OCSP material is not archived. Operator independence is declared,
not audited. The strongest next step is a dual-root-signed bundle rotation with archived
revocation evidence and a transparency-log witness. Sigstore trust-root maintainers are
the best prospective collaborators for schema compatibility and rotation review.
