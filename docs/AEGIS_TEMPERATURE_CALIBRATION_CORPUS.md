# AEGIS authenticated calibration corpus import

Status: deterministic HoloDeck proof; offline corpus storage only; not field
validation, candidate acceptance, installation, or deployment.

## Increment

PR #211 deliberately stops at an authenticated admission that performs no
write. This follow-up adds the narrow consumer of that record. It re-runs the
complete development, field-review, and label-admission verification chain,
then snapshots the same protected four-frame recording again.

Only after the signed digest, byte count, frame count, corpus ID, case ID, and
labels all agree does one case become visible. A committed case is one
directory containing the exact recording, admission statement, and a
content-addressed import receipt. Case directories are never updated. A POSIX
exclusive lock serializes duplicate checks, complete files are flushed in a
private staging directory, and one rename publishes the case atomically.

The corpus metadata is immutable. The index is reconstructed from verified
case receipts rather than maintained as a second mutable source of truth.
Duplicate case IDs and recording digests fail closed.

Success reaches only
`CALIBRATION_CASE_IMPORTED_FOR_OFFLINE_ANALYSIS`. It explicitly leaves field
and production validation, candidate acceptance and installation, runtime,
deployment, hardware, network, storage-control, and automatic-promotion
authority false.

## HoloDeck evidence

TP-EXP-0032 covers nine deterministic cases:

- one exact authenticated import;
- duplicate case ID and duplicate recording digest;
- signed corpus-identity drift;
- authority-field tampering;
- recording drift after review;
- expired admission;
- unsafe corpus permissions; and
- an unexpected corpus entry.

Exactly one case directory commits. Eight cases HOLD. No partial or duplicate
case directory, validation claim, acceptance, installation, deployment,
hardware action, runtime write, private-key input, or TruePanel signer call is
produced.

Preserved evidence:
[`docs/evidence/aegis-temperature-calibration-corpus-v1.json`](evidence/aegis-temperature-calibration-corpus-v1.json).

## Prior-Art Field Report

| Candidate | Inspected capability and maturity | Platform / dependency fit | License and provenance | Decision |
|---|---|---|---|---|
| [DVC Objects](https://github.com/treeverse/dvc-objects) | Its object-database layer requires upload, download, listing, copying, and quasi-atomic rename and has its own tests and active repository. | Mature multi-backend storage is useful for larger corpora, but `fsspec`, remote adapters, and credential surfaces are disproportionate for a bounded local NAS evidence set. | Apache-2.0. No code copied. | **Adapt the staging-plus-rename invariant** using Python/POSIX primitives already present; do not add the dependency. |
| [OpenLineage dataset version facet](https://github.com/OpenLineage/OpenLineage/blob/main/spec/facets/DatasetVersionDatasetFacet.json) | The actual JSON Schema makes dataset version an explicit required string and keeps lineage facets separate from bytes. | Excellent interoperability vocabulary when TruePanel exports lineage, but an event producer/backend adds no value to one local append-only corpus. | Apache-2.0. No schema copied. | **Adapt explicit corpus/case identity and receipt lineage** behind TruePanel's schema. OpenLineage maintainers remain the best collaboration opportunity. |
| [MLCommons Croissant](https://github.com/mlcommons/croissant/blob/main/docs/croissant-spec.md) | The specification binds dataset metadata to file resources and recommends SHA-256 for robust verification; the repository includes implementation, verifier, examples, CI, and broad integrations. | Strong future export format, but JSON-LD and `mlcroissant` are heavier than the four-frame private corpus needs. | Implementation Apache-2.0; specification CC BY-ND 4.0 with attribution considerations. No text, schema, or code copied. | **Defer adoption**; preserve the digest/resource mapping needed for a later exporter. |
| [lakeFS](https://github.com/treeverse/lakeFS) | Branch/commit semantics and atomic data-lake transactions are a credible solution for large shared corpora. | Requires a service, database/object-store integration, authentication, and operational ownership far beyond this appliance-local case set. | Repository history must be reviewed carefully because upstream announced a 2026 license transition. No code copied. | **Reject for runtime use**; revisit only if TruePanel grows into a shared multi-writer evidence lake. |
| Existing TruePanel field workflow | Already provides consent, sanitized intake, review, freeze, replay, and assessment with extensive tests. | Native and dependency-free, but its mutable aggregate manifest predates authenticated per-case admission. | TruePanel MIT code. | **Reuse validation concepts, not the mutable write path.** The new adapter is separately replaceable. |

### Security and maintenance comparison

DVC and lakeFS could save development time once remote storage, branching, or
multi-host concurrency is required. Today they would introduce substantially
more code, credentials, and update burden than they remove. Croissant and
OpenLineage are better fits for export and cross-project interchange than for
the local commit boundary. The implemented standard-library adapter is small,
testable, has no network path, and is wrapped by the TruePanel-owned
`import_temperature_calibration_case` interface so it can be replaced later.

## Failed approaches and corrected assumptions

- **A mutable aggregate manifest is not the safest commit primitive.** A crash
  between recording and manifest writes creates two truths. Per-case staging
  plus rename makes visibility the commit point.
- **A valid admission digest is not enough for a consumer.** The importer must
  independently bind the signed recording byte and frame counts; PR #211's
  result now exposes those already-signed values.
- **Case-ID uniqueness is not content uniqueness.** Both case IDs and recording
  digests are checked under the same lock.
- **A filesystem write is not field validation.** Mission Control labels the
  committed case as offline-analysis material and preserves every negative
  authority flag.

## Limits and next step

The implementation is POSIX-specific (`flock`, `O_NOFOLLOW`, ownership and
mode checks, directory `fsync`). It is not a portable Windows store, a remote
multi-host database, a legal-consent system, or a corpus withdrawal mechanism.
The checkride uses disposable keys and synthetic evidence; no JT key or field
recording exists in the repository.

Next, provision JT's protected development public roster and complete the real
development, field-review, and admission signatures. Then run exactly one
separately authorized sanitized recording through this importer and inspect
the committed receipt before proposing any assessment or validation step.
