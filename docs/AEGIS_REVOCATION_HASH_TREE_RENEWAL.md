# AEGIS revocation archive hash-tree renewal

This increment migrates the complete preserved revocation archive from SHA-256 to SHA-512 before the old digest-policy deadline. It re-verifies the predecessor CRL/OCSP archive, rehashes all 11 source objects and the complete prior timestamp sequence, proves every object in a domain-separated Merkle tree, then verifies an RFC 3161 SHA-512 timestamp over the exact root.

The record is deliberately described as ERS-inspired. It is not ASN.1 EvidenceRecord syntax and is not RFC 4998 wire-compatible. It grants no runtime, storage, network, deployment, or hardware authority.

## Architecture and contract

| Stage | Machine-verifiable evidence | Fail-closed conditions |
|---|---|---|
| Predecessor | Exact CRL/OCSP packages and combined renewal token are cryptographically reverified | Missing, changed, untrusted, or mismatched predecessor |
| Migration | SHA-512 hashes cover 11 objects plus a length-framed complete prior timestamp sequence | Missing object, duplicate label, tamper, or incomplete sequence |
| Tree | RFC 9162-shaped, domain-separated SHA-512 tree and 11 inclusion paths | Invalid path or root mismatch |
| Continuity | Generation advances 2→3 and archive chain advances 1→2 | Skip, replay, or wrong predecessor |
| Time | RFC 3161 token uses SHA-512 and covers the raw 64-byte root before the earliest deadline | SHA-256 downgrade, wrong bytes, invalid TSA, or late token |

HoloDeck exercises ten paths: one trusted migration and nine HOLD outcomes. The trusted path preserves the existing 8/8 recovery matrix and the fan-degradation shared-cooling result at sample 19 versus isolated thresholds at sample 46, a 27-sample lead.

## Prior-Art Field Report

| Candidate | What was inspected | Fit and maturity | License / dependency | Recommendation |
|---|---|---|---|---|
| [RFC 4998 Evidence Record Syntax](https://www.rfc-editor.org/rfc/rfc4998) | Hash-tree renewal requirements and complete prior ArchiveTimestampSequence binding | Normative architecture; explicitly requires rehashing data and prior sequence when an algorithm weakens | IETF standard; no runtime dependency | Adapt semantics now; do not claim wire compatibility |
| [ETSI DSS Evidence Record](https://ec.europa.eu/digital-building-blocks/DSS/webapp-demo/doc/dss-documentation.html) | `ASN1EvidenceRecordRenewalDigestBuilder` and tests, including SHA-512 renewal and detached content | Mature, maintained, well-tested Java implementation and strongest future behavior/interoperability oracle | LGPL-2.1-or-later; substantial JVM/XML/ASN.1 stack | Collaborate/interop-test later; avoid embedding its dependency graph in TruePanel |
| [Bouncy Castle ERS](https://downloads.bouncycastle.org/java/docs/bcpkix-jdk18on-javadoc/org/bouncycastle/tsp/ers/ERSEvidenceRecord.html) | `ERSEvidenceRecord.renewHash`, which validates old data and binds data plus prior chains into a new chain | Mature cryptographic library with direct RFC 4998 APIs | Permissive Bouncy Castle license; Java dependency | Use as a second interop oracle if ASN.1 ERS export becomes required |
| [RFC 9162 Certificate Transparency v2](https://www.rfc-editor.org/rfc/rfc9162) | Deterministic non-power-of-two tree shape and leaf/node domain separation | Small, auditable, dependency-free transferable primitive | IETF standard; no runtime dependency | Adopt the tree shape and domain separation with SHA-512 |

No third-party code was copied. TruePanel owns the narrow interface and implementation, which uses Python's standard `hashlib`; the external work supplied specifications and testable architectural invariants. This avoids ambiguous provenance and keeps replacement straightforward.

Rejected paths include importing a Java ERS stack solely for an internal manifest, timestamping the JSON manifest instead of the raw tree root, carrying forward only the latest renewal token, and presenting an ERS-inspired JSON record as standards-conformant ASN.1. Each adds dependency weight, loses custody evidence, or overstates interoperability.

The best collaboration opportunity is with the ETSI DSS maintainers: define fixtures that both DSS and TruePanel can validate before any future ASN.1 EvidenceRecord export. Bouncy Castle is the best independent cross-check.

## Evidence and safety

The deterministic result is preserved at `docs/evidence/aegis-temperature-revocation-hash-tree-renewal-v1.json`. It records 11/11 archive objects and proofs, four real RFC 3161 tokens, zero downgrade/tamper/late acceptances, zero retained fixture keys, and zero deployment, runtime, or hardware actions.

This work is simulation-only. It was not deployed to BattleStation, did not access live hardware, did not modify TrueNAS, and performed no storage or network mutation.
