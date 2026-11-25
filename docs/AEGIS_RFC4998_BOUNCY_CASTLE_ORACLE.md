# AEGIS RFC 4998 Bouncy Castle oracle

## Outcome

The preserved TruePanel RFC 4998 single-detached-object fixture now has a
version-pinned independent validation contract using Bouncy Castle Java 1.86.
The CI oracle parses the exact DER, round-trips it byte-for-byte, verifies the
detached data is present, verifies the RFC 3161 timestamp signature, and
validates the TSA certificate path against the preserved fixture root at the
timestamp generation time.

The same executable rejects wrong detached data, truncated DER, and a different
trust root. Its deterministic receipt is compared byte-for-byte with
`docs/evidence/aegis-rfc4998-bouncycastle-receipt-v1.json`; CI fails if the
oracle version, fixture identity, result fields, or authority floors drift.

This proves one preserved fixture against one independent implementation. It
does not make an arbitrary active record trusted, does not establish TSA clock
quality, and does not grant production, deployment, runtime, network, storage,
or hardware authority.

## Architecture

| Boundary | Responsibility |
|---|---|
| TruePanel fixture generator | Produces one bounded RFC 4998 DER record, detached data, expected root, and an unrelated negative root; discards all private keys. |
| Preserved fixture | Content-addresses the exact DER and detached data used by the oracle. |
| Bouncy Castle adapter | Lives only under `development/interop`; parses and validates through public ERS, CMS, certificate, and PKIX APIs. |
| CI contract | Pins Bouncy Castle 1.86, generates the deterministic receipt, compares it with the reviewed receipt, and uploads the receipt as a workflow artifact. |
| Mission Control | Separates “fixture oracle passed” from “active record pending” and retains every operational denial. |

## Prior-Art Field Report

| Candidate | Actual code or documentation inspected | Capability, maturity, and fit | License / dependency weight | Recommendation |
|---|---|---|---|---|
| [Bouncy Castle Java 1.86](https://www.bouncycastle.org/download/bouncy-castle-java/) | [`ERSEvidenceRecord`](https://github.com/bcgit/bc-java/blob/r1rv86/pkix/src/main/java/org/bouncycastle/tsp/ers/ERSEvidenceRecord.java), `ERSByteData`, and `ERSTest` at tag `r1rv86` | Mature RFC 4998 parser, detached-data presence checks, renewal logic, timestamp signature verification, active tests, and a September 2026 hardening release. Directly closes the independent-parser gap. | MIT-style Bouncy Castle license. Three version-pinned Maven artifacts; development/CI only, no TruePanel runtime dependency. | **Adopt as the first external oracle behind a TruePanel-owned executable contract.** |
| [ETSI DSS Evidence Record Syntax](https://ec.europa.eu/digital-building-blocks/DSS/webapp-demo/doc/dss-documentation.html#EvidenceRecordSyntax) | Evidence-record validator tests and renewal digest-builder documentation | Strong second implementation with broad validation reporting. Valuable precisely because it is independent of Bouncy Castle and TruePanel. | LGPL-2.1-or-later and a much larger Java dependency graph. | **Use next as a second CI oracle; do not embed in the appliance runtime.** |
| [OpenSSL `ts`](https://docs.openssl.org/master/man1/openssl-ts/) | Existing TruePanel adapter and generated fixture path | Excellent RFC 3161 and PKIX primitive, but not an RFC 4998 semantic parser. | Apache-2.0; already present. | **Retain as producer-side self-verification, never count it as the independent oracle.** |
| [RFC 4998](https://www.rfc-editor.org/rfc/rfc4998) | ASN.1 module and single-object validation rules | Normative source of the wire contract and reduced-hash-tree omission used by the fixture. | IETF document; no dependency. | **Continue as the normative contract.** |

### Rejected paths

- Copying Bouncy Castle ERS source into TruePanel was rejected. It would remove
  validator independence and create an unnecessary maintenance fork.
- Adding Bouncy Castle to the TruePanel runtime wheel was rejected. The oracle
  belongs in development and CI; the appliance remains Python/OpenSSL only.
- Treating a passed static fixture as proof for every future active record was
  rejected. Mission Control continues to require per-record validation.
- Using only ASN.1 parse success was rejected because it does not prove detached
  content presence, CMS signature validity, or the intended trust anchor.
- Making ETSI DSS the first integration was deferred because its heavier LGPL
  stack saves less verified development time for this narrow first oracle.

## Provenance

No Bouncy Castle or ETSI DSS source code, test vector, or implementation was
copied. The Maven project is a TruePanel-owned adapter calling public APIs.
Bouncy Castle artifacts remain unmodified external CI dependencies pinned to
1.86. The repository retains Bouncy Castle's name and version in the receipt
and this report; its license is available at the upstream `r1rv86` tag.

## Measurements

- independent implementations completed: 1;
- exact DER parses: 1;
- exact DER round trips: 1;
- detached-data presence validations: 1;
- timestamp signature validations: 1;
- PKIX validations at timestamp time: 1;
- wrong-data acceptances: 0;
- truncated-record acceptances: 0;
- wrong-root acceptances: 0;
- production/deployment/hardware authority: 0;
- inherited shared-cooling lead: 27 samples (19 versus 46).

## Strongest next step

Add ETSI DSS as a second pinned oracle over the same immutable fixture and
require both independent receipts for format-level interoperability. Then add a
per-record adapter so an active archive must obtain fresh oracle receipts before
Mission Control can move it beyond `PENDING`.
