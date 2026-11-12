# AEGIS timestamp trust rotation

## Outcome

AEGIS now requires each timestamp trust-bundle generation to advance exactly one step
and be signed over identical canonical bytes by both the predecessor and successor
governance roots. The statement binds both bundle digests, both root fingerprints, a
two-hour ceremony window, and fresh CRL or OCSP evidence for every outgoing TSA
operator. Missing, stale, duplicated, or unknown revocation evidence fails closed.

The ceremony authorizes timestamp trust rotation only. It grants no validation,
installation, deployment, capture, runtime, storage, network, or hardware authority.

## HoloDeck evidence

Seven deterministic paths trust one dual-signed consecutive transition and hold missing
predecessor or successor signatures, a generation gap, incomplete or stale revocation
evidence, and authority escalation. Two temporary Ed25519 fixture keys are deleted.
Recovery coverage remains 8/8; shared cooling appears at sample 19 versus isolated
thresholds at sample 46, a 27-sample lead at 0.95 evidence-weight confidence.

Evidence: `docs/evidence/aegis-temperature-timestamp-trust-rotation-v1.json`

## Prior-Art Field Report

| Candidate | Capability inspected | Fit, maturity, and security | License / obligations | Recommendation |
| --- | --- | --- | --- | --- |
| TUF root update | Exact N to N+1 versioning plus predecessor and successor thresholds | Mature, audited model; directly closes self-authorized rotation | Specification; concepts only | **Adapt dual-root continuity.** |
| RFC 6283 ERS | Archive timestamp chains may carry certificates, CRLs, and OCSP responses | Strong long-term evidence model; full ASN.1 evidence records are premature here | IETF standard | **Adapt content-bound revocation archives now; evaluate ERS later.** |
| ETSI AdES validation | Identifies certificates, CRLs, OCSP responses, timestamps, and evidence records as validation objects | Mature compliance framework but heavyweight XML/report stack | ETSI specification | **Adapt validation-object identity, not the report format.** |
| Sigstore TSA policy | Requires trusted, non-revoked TSU certificates and explains long-term revalidation | Direct operational fit; Sigstore services remain unnecessary | Apache-2.0 documentation/code; concepts only | **Adopt the revocation requirement.** |
| Sigstore TrustedRoot | Retains expired historical authorities and selects by witnessed time | Strong interoperability direction | Apache-2.0 schema; no schema copied | **Keep future compatibility as a design target.** |

Sources inspected 2026-11-08: [TUF root update](https://github.com/theupdateframework/specification/blob/master/tuf-spec.md),
[RFC 6283](https://www.rfc-editor.org/rfc/rfc6283.html),
[ETSI TS 119 102-2](https://www.etsi.org/deliver/etsi_ts/119100_119199/11910202/01.04.01_60/ts_11910202v010401p.pdf),
[Sigstore TSA policy](https://github.com/sigstore/timestamp-authority/blob/main/docs/tsa-policy.md), and
[Sigstore TrustedRoot](https://github.com/sigstore/protobuf-specs/blob/main/protos/sigstore_trustroot.proto).

## Provenance, rejected paths, and risks

No external source, schema, package, service, credential, key, CRL, OCSP response, or
dataset was copied. Existing OpenSSH verification stays behind a TruePanel interface.
The implementation records evidence digests rather than shipping a network fetcher.

Rejected: successor self-authorization; accepting N to N+2; using only current online
revocation state; treating a URI as preserved evidence; silently skipping one outgoing
operator; and automatically activating a rotated bundle.

The fixture proves content and policy enforcement, not CA freshness, responder custody,
or human keyholder independence. Revocation objects are digest-bound but not yet embedded
or protected by a later archive timestamp. The strongest next step is a content-addressed
revocation-evidence package with DER parsing, certificate/serial binding, and a renewal
timestamp before the evidence expires. Sigstore timestamp-authority and TUF maintainers
are the strongest prospective collaborators.
