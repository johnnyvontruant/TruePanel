# AEGIS RFC 4998 interoperability fixture

## Outcome

AEGIS can now export and self-verify a bounded RFC 4998 `EvidenceRecord`
containing one SHA-512 RFC 3161 archive timestamp over one detached archive
root. The fixture is eligible for independent validation, but it is not called
interoperable or production trusted until the exact DER is accepted by at
least one independent implementation.

The implementation is simulation-only. It performs no deployment, network,
storage, service, or hardware action.

## Profile and trust boundary

The supported profile is deliberately narrow:

- `EvidenceRecord.version` is exactly 1;
- `digestAlgorithms` contains exactly SHA-512;
- one `ArchiveTimeStampChain` contains exactly one `ArchiveTimeStamp`;
- `reducedHashtree` is absent because the timestamp covers one detached data
  object directly;
- the archive timestamp is a CMS `ContentInfo`, extracted from a generated
  RFC 3161 response;
- OpenSSL first accepts the full object as DER, then AEGIS parses the bounded
  profile and verifies the embedded token over the exact 64-byte detached
  root using a protected trust anchor and policy;
- self-verification only permits export to an external oracle. It never grants
  timestamp trust rotation, production, deployment, runtime, storage,
  network, or hardware authority.

The HoloDeck checkride covers a valid record plus wrong-root, truncated DER,
wrong-version, digest-downgrade, token-tamper, trailing-data, and wrong-CA
paths. Exactly one of eight paths is self-verified; all seven adversarial paths
hold. The inherited cooling scenario remains bound at sample 19, 27 samples
before isolated thresholds at sample 46.

Preserved evidence:
`docs/evidence/aegis-temperature-rfc4998-interoperability-v1.json`.

## Prior-Art Field Report

| Candidate | Actual material inspected | Capability and fit | License / dependency | Decision |
|---|---|---|---|---|
| [RFC 4998](https://www.rfc-editor.org/rfc/rfc4998) | ASN.1 module, `EvidenceRecord`, `ArchiveTimeStamp`, renewal, and single-data-object processing rules | Normative wire contract; directly supports omitting the reduced hash tree for the single detached object profile | IETF document; no runtime dependency | **Adopt the wire contract.** Implement only the bounded profile needed for a replaceable fixture. |
| [Bouncy Castle ERS](https://github.com/bcgit/bc-java/tree/main/pkix/src/main/java/org/bouncycastle/tsp/ers) | `ERSEvidenceRecordGenerator` and ERS regression tests, including SHA-2 parameter handling | Mature generation and validation oracle; Java is not otherwise in TruePanel's runtime | Permissive Bouncy Castle license; substantial Java dependency if embedded | **Use as an external oracle, do not embed.** No code copied. |
| [ETSI DSS Evidence Record Syntax](https://ec.europa.eu/digital-building-blocks/DSS/webapp-demo/doc/dss-documentation.html#EvidenceRecordSyntax) | Evidence-record validation and renewal-digest documentation plus ASN.1 validator tests | Strong independent validator and useful renewal digest builders; intentionally does not create evidence records | LGPL-2.1-or-later; large Java stack | **Validate externally, do not adopt at runtime.** No code copied. |
| [OpenSSL `ts`](https://docs.openssl.org/master/man1/openssl-ts/) and [`asn1parse`](https://docs.openssl.org/master/man1/openssl-asn1parse/) | Installed command behavior for CMS token extraction, RFC 3161 verification, and generic DER parsing | Already used behind TruePanel-owned adapters; provides deterministic local cryptographic checks without a new package | Apache-2.0; existing system dependency | **Adopt behind the existing adapter.** This is self-verification, not an independent interoperability result. |
| [RFC 9162 Merkle Tree Hash](https://www.rfc-editor.org/rfc/rfc9162) | Domain-separated tree construction used by the predecessor experiment | Excellent internal multi-object tree, but not itself an RFC 4998 ASN.1 codec | IETF document; no runtime dependency | **Retain internally.** Do not confuse an ERS-inspired tree with wire interoperability. |

### Rejected shortcuts

- A general-purpose ASN.1 dependency was rejected for this increment: the
  supported schema is tiny, input is bounded, and an added codec would not
  supply independent validation.
- Copying Bouncy Castle or DSS code was rejected: their strongest value here
  is independence as external oracles, and embedding either would add license
  and platform weight without proving cross-implementation acceptance.
- Calling a locally generated object interoperable after OpenSSL plus the
  TruePanel parser agree was rejected as circular evidence.
- Importing public CA roots or allowing arbitrary digest algorithms was
  rejected because it silently expands authority and downgrade surface.

## Provenance and collaboration opportunity

No third-party source code or test vectors were copied. The new DER encoder,
bounded parser, checkride, and UI contract are TruePanel-owned. The only
adapted material is the public RFC 4998 structure and the architectural idea
of using independent libraries as conformance oracles.

The best collaboration opportunity is with the Bouncy Castle ERS maintainers:
their generator and validator can provide a small, repeatable cross-library
fixture exchange without coupling TruePanel to a Java runtime. ETSI DSS is the
second oracle because its validation path and test corpus provide a meaningfully
independent implementation.

## Reproduction

```sh
pytest -q tests/test_aegis_temperature_rfc4998_interop_fixture.py
python -c "from truepanel.holodeck.aegis_temperature_rfc4998_interop_fixture import run_temperature_rfc4998_interop_checkride as run; print(run()['measurements'])"
python -m truepanel.hangar validate --root .
node --check truepanel/web/static/reliability-view.js
```

## Open gate

Run the exact generated DER and detached SHA-512 root through current Bouncy
Castle and ETSI DSS validators, preserve their versioned receipts, and add
their acceptance as a second source of truth. Until then the Mission Control
gate must continue to show external validation as `PENDING` and production
trust as `NO`.
