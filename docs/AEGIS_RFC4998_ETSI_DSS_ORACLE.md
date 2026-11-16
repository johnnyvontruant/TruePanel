# AEGIS RFC 4998 ETSI DSS oracle

## Outcome

The immutable RFC 4998 single-detached-object fixture is now exercised by a
second version-pinned CI oracle: European Commission Digital Signature Services
(DSS) 6.5.1. The TruePanel-owned adapter supplies the exact DER, detached data,
and explicit fixture trust root to DSS's public evidence-record validation API.
It preserves a deterministic receipt only when DSS reports a valid structure,
intact detached-data binding, intact timestamp imprint, valid timestamp
signature, and a certificate chain reaching the intended root.

The same executable verifies three fail-closed paths: changed detached data is
not intact, truncated DER cannot instantiate the validator, and an unrelated
root does not become trusted. CI byte-compares the generated receipt with the
reviewed receipt and uploads it as an artifact.

This closes the static-fixture second-oracle gap. It does not validate an active
record, establish TSA clock quality, or grant production, deployment, storage,
network, runtime, or hardware authority. Mission Control therefore shows two
fixture validators rehearsed while the active-record state remains `PENDING`.

## Architecture and provenance

| Boundary | Contract |
|---|---|
| Preserved fixture | The same content-addressed DER, detached bytes, intended root, and unrelated root already reviewed by the Bouncy Castle oracle. |
| TruePanel DSS adapter | Calls `ASN1EvidenceRecordValidator`, `setDetachedContents`, `CommonCertificateVerifier`, and `CommonTrustedCertificateSource`; it contains no copied DSS implementation. |
| Development dependency | Pins `dss-evidence-record-asn1` and `dss-validation` 6.5.1 under `development/interop`; the Python appliance and wheel gain no Java dependency. |
| CI receipt | Fails on dependency drift, fixture drift, result drift, wrong-data acceptance, malformed-DER acceptance, or trust-root substitution. |
| Mission Control | Distinguishes two passed fixture oracles from an unvalidated active record and retains all authority denials. |

DSS is LGPL-2.1-or-later. The integration dynamically resolves unmodified Maven
artifacts for development and CI, identifies the upstream product and version,
and copies no upstream source or test vector. The adapter remains behind a
TruePanel-owned executable and receipt schema so it can be replaced.

## Prior-Art Field Report

Research was refreshed against upstream source and documentation on 2026-11-15.

| Candidate | Actual material inspected | Capability and maturity | License / weight / security | Build-versus-adopt decision |
|---|---|---|---|---|
| [ETSI DSS 6.5.1](https://ec.europa.eu/digital-building-blocks/sites/spaces/DIGITAL/pages/467109114/DSS%2Breleases) | `EvidenceRecordValidatorTest`, `ASN1EvidenceRecordValidator`, `ASN1EvidenceRecordAnalyzer`, diagnostic wrappers, Maven module graph, and tag `6.5.1` (`98ab6c1`) | Current October 2026 release; native RFC 4998 recognition, detached-content validation, trust-source configuration, rich diagnostic reports, extensive ERS tests, and active maintenance. Directly closes the remaining second-oracle gap. | LGPL-2.1-or-later; substantial transitive Java graph; CI-only; explicit trust source avoids the system trust store; no credentials or network validation sources. | **Adopt public validation APIs behind a TruePanel adapter. Do not embed in the appliance runtime.** |
| [Bouncy Castle 1.86](https://www.bouncycastle.org/download/bouncy-castle-java/) | Existing `ERSEvidenceRecord`, CMS, and PKIX oracle | Leaner direct ERS primitives and exact DER round-trip; mature and actively maintained. | Permissive license; three pinned CI artifacts. | **Retain as the first oracle.** Its lower-level path complements DSS diagnostics. |
| [OpenSSL `ts`](https://docs.openssl.org/master/man1/openssl-ts/) | Existing producer-side RFC 3161 and PKIX path | Strong timestamp primitive but not an RFC 4998 semantic validator. | Apache-2.0; already present. | **Retain for local generation/self-checks; never count as a second ERS oracle.** |
| [AdES Validation Report](https://www.etsi.org/deliver/etsi_ts/119100_119199/11910202/01.03.01_60/ts_11910202v010301p.pdf) | DSS report model and structured diagnostic output | Useful future interchange format for per-record receipts, but broader and less deterministic than the current narrow JSON contract. | ETSI specification; DSS generation adds report complexity. | **Adapt semantics later; do not replace the narrow reviewed receipt yet.** |

### Rejected paths and challenged assumptions

- Copying or modifying DSS source was rejected because it would create a license
  and maintenance fork while weakening oracle independence.
- Adding DSS to the TruePanel runtime was rejected because a large Java graph on
  the NAS saves no runtime development time for an offline interoperability gate.
- Enabling AIA, OCSP, CRL, or the host trust store was rejected. The fixture is
  deterministic and must trust only its explicit root without network access.
- Treating two wrappers around Bouncy Castle internals as two cryptographically
  independent primitive implementations would overstate the result. DSS is
  counted as a second independent validation product and policy/reporting path,
  not as a second cryptographic provider; both currently resolve Bouncy Castle.
- Promoting all active records because one immutable fixture passed twice was
  rejected. Fresh receipts must bind each active record and detached payload.

## Measurements

- external validation products rehearsed: 2;
- exact immutable fixtures accepted by both: 1;
- DSS structural/data/imprint/signature/trust checks passed: 5/5;
- wrong-data, truncated-DER, and wrong-root acceptances: 0/3;
- remaining fixture-oracle gaps: 0;
- active-record external validation: `PENDING`;
- production/deployment/runtime/hardware authority: 0;
- inherited shared-cooling detection lead: 27 samples (19 versus 46);
- accepted Recovery Coverage Matrix: 8/8 trusted paths.

## Most promising collaboration

The strongest technical discussion is with the ETSI DSS maintainers: contribute
or mutually review a minimal single-detached-object RFC 4998 vector and clarify
portable diagnostic assertions across DSS and direct ERS implementations. No
external contact or posting was made.

## Strongest next step

Create a per-record oracle envelope that binds both fresh receipts to the active
EvidenceRecord hash, detached-object hash, validator versions, validation time,
and reviewed policy. Mission Control must continue to hold until those exact
receipts exist; fixture receipts must never be reused as active-record proof.
