# AEGIS Confirmed Recording Intake

## Outcome

This increment accepts exactly one operator-supplied, sanitized Black Box recording only after independently reconstructing the exact offline field-checkride confirmation. It verifies the confirmation statement, SSHSIG, immutable receipt, plan identity, custody declaration, canonical bytes, privacy boundary, seven-signal contract, 48 monotonic samples, and twelve-sample stable baseline before writing a content-addressed intake receipt.

Success reaches only `READY_FOR_LABEL_BLIND_PASSIVE_REPLAY`. The source recording is never copied, rewritten, tailed, deleted, labeled, or replayed. TruePanel performs no capture, retains no source path, accesses no live host, and receives no field-checkride, validation, promotion, deployment, storage, network, runtime, or hardware authority.

## HoloDeck proof

- Thirteen deterministic paths: one intake ready and twelve HOLD.
- HOLD covers operator HOLD, confirmation-receipt substitution, noncanonical bytes, a missing signal, unstable baseline, nonmonotonic time, raw identity, embedded labels, a TruePanel-capture claim, unsafe permissions, symlink input, and duplicate intake replay.
- The accepted fixture contains 48 samples, a twelve-sample stable baseline, and all seven required signals.
- The accepted Recovery Coverage Matrix remains 8/8 trusted with zero gaps.
- Shared cooling remains targeted at sample 19 versus isolated threshold sample 46: 27 samples earlier.
- Source paths retained, recordings captured or replayed, BattleStation accesses, field-checkride authorizations, validations, deployments, hardware actions, and runtime writes: zero.
- Preserved evidence: `docs/evidence/aegis-temperature-confirmed-recording-intake-v1.json` (`1a8ae002db2b3ac305d90b3271281c4c0596931571de957077dc60f0c0fbd8e5`).

## Prior-Art Field Report

| Candidate | Actual code or specification inspected | Capability, maturity, fit, security, licence | Recommendation |
|---|---|---|---|
| [BagIt RFC 8493](https://www.rfc-editor.org/rfc/rfc8493.html) and [bagit-python](https://github.com/LibraryOfCongress/bagit-python/blob/4bd2713cedbe1f8e634567c20ef0dded9622011d/src/bagit/__init__.py) | Payload manifests bind every transferred file to a checksum; Payload-Oxum provides byte and file-count completeness. The implementation distinguishes quick payload-count validation from full checksum validation and has extensive validation tests. | Stable IETF format, widely used for transfer custody; bagit-python is Public Domain/CC0. A directory package and multi-file manifest are excessive for one bounded JSON recording. | Adapt fixity-plus-size semantics; do not add the package. |
| [OCFL 1.1 inventory schema](https://github.com/OCFL/spec/blob/2637866930ce26c52b50510aa91cbed9c1c4b0a4/1.1/spec/inventory_schema.json) | A strict JSON inventory uses SHA-256/SHA-512 digests, content-addressed manifests, optional supplemental fixity, and rejects additional properties. | Mature preservation specification with validator ecosystems; specification is CC BY 4.0. Full versioned object layout adds storage semantics AEGIS must not acquire. | Adapt strict fields, digest identity, and non-replacement; reject the storage layout. |
| [RO-Crate 1.3](https://www.researchobject.org/ro-crate/specification.html) and [source](https://github.com/ResearchObject/ro-crate/blob/7cbb4e2eb41ac3eeb27d06fdae955d3303cd7d5a/docs/_specification/1.3/appendix/relative-uris.md) | Self-describing dataset metadata can declare content size, encoding, licence, relationships, and acceptable archival entities. | Active research-data community; specification and tooling are Apache-2.0. JSON-LD expansion and broad descriptive metadata would increase parser and privacy surface. | Adapt the self-describing manifest boundary only; no JSON-LD dependency. |
| [W3C PROV](https://www.w3.org/TR/prov-overview/) | Separates entities, activities, and responsible agents so custody and transformations can be assessed independently. | W3C Recommendation family with broad implementations; conceptual model is platform-neutral. It records asserted provenance, not proof. | Use the entity/activity distinction to keep operator supply separate from TruePanel verification; never treat custody text as cryptographic proof. |
| [in-toto Statement v1](https://github.com/in-toto/attestation/blob/50bf01716982189898823e90586075f37cd9bb7d/spec/v1/statement.md) | Immutable subjects are matched by digest and typed predicates separate artifact identity from claims. | CNCF ecosystem, Apache-2.0, multi-language tests; full attestation machinery remains unnecessary for this local gate. | Retain digest-bound subject semantics behind the TruePanel-owned receipt. |
| [OpenTelemetry hardware conventions](https://github.com/open-telemetry/semantic-conventions/tree/main/model/hardware) | Supplies interoperable fan-speed, speed-ratio, and temperature names and units. | Active Apache-2.0 project; hardware conventions remain developmental. | Keep the seven names behind the existing replaceable TruePanel contract; do not import an SDK or collector. |

### Build versus adopt

The useful external shortcuts are semantic: BagIt contributes fixity and completeness; OCFL contributes strict content-addressed inventory behavior; RO-Crate contributes a self-describing dataset boundary; W3C PROV clarifies custody roles; in-toto binds claims to immutable subjects; and OpenTelemetry supplies signal vocabulary. TruePanel keeps a compact standard-library implementation because the accepted object is a single bounded file, the privacy schema is intentionally closed, and importing a preservation repository, JSON-LD processor, or telemetry collector would add dependency and attack surface without verified benefit.

No third-party code, package, schema, service, credential, key, or dataset was incorporated. No new attribution file is required; provenance and licences are recorded here. The most promising collaboration opportunity is the BagIt/OCFL preservation community: ask how a one-file operational-evidence handoff should express fixity, byte count, custody, and privacy without pretending to be a long-term archive.

## Failed and rejected paths

- Trusting the confirmation receipt digest without reverifying its statement and SSHSIG was rejected.
- Allowing more than one recording per confirmation was rejected; the registry is exclusive and keyed by confirmation receipt.
- Semantic JSON equality was rejected because whitespace and alternate encodings would retain meaning while changing bytes.
- Retaining the source path in evidence was rejected as both privacy leakage and an accidental live-source capability.
- Treating “operator supplied” as proof of sanitization was rejected; exact fields and recursive forbidden-identity checks are required.
- Accepting labels at intake was rejected to preserve label-blind replay.
- Importing BagIt, OCFL, RO-Crate, or OpenTelemetry runtimes was rejected as unnecessary dependency weight.
- Copying the recording into a managed corpus was rejected; this step writes only the digest-bound receipt.

## Open risks and next step

The fixture proves contract enforcement, not real field accuracy or real privacy review. A pseudonymous profile can still become identifying when combined with external information. POSIX custody is not independently witnessed, and the current development roster is not a two-person threshold.

The next safe increment is an independent label-blind passive replay receipt over this intake. It should reconstruct the detector result without exposing outcome labels, prove the shared-cooling hypothesis and 27-sample lead, preserve evidence, and still grant no field validation, promotion, deployment, capture, or hardware authority.
