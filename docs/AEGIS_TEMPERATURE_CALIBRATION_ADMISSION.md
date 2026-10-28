# AEGIS temperature calibration admission

Reviewed: 2026-10-16

## Decision

The signed field-review receipt proves that JT reviewed one exact sanitized
recording, but it does not authenticate the labels later supplied to the
calibration corpus. The new admission boundary therefore creates a separate,
short-lived statement over the exact field-review receipt, recording digest,
corpus and case IDs, expected shared-cooling outcome, system profile, workload
class, and isolated-threshold landmark.

JT's detached OpenSSH SSHSIG uses a new interpretation namespace and the same
protected Ed25519 trust root. Success reaches only
`CALIBRATION_CASE_AUTHENTICATED_FOR_CORPUS_IMPORT`. Evaluation performs no
corpus write and grants no field validation, candidate acceptance, installation,
runtime, deployment, storage, network, hardware, or automatic-promotion
authority. Mission Control presents the missing real signature honestly.

The accepted Recovery Coverage Matrix remains **8/8 trusted with zero gaps**.
The temperature successor remains a **9/9 unaccepted, uninstalled candidate**.

## HoloDeck proof

`run_temperature_calibration_admission_checkride()` uses only disposable
fixture keys and deterministic recordings. Twelve cases produce one public
statement ready for offline signing, two authenticated import-only results,
and nine `HOLD` results. Outcome or profile label drift, unknown label fields,
recording drift, authority escalation, namespace reuse, a foreign key under the
same principal, unsafe permissions, and expiry all fail before any write.

Preserved evidence:
[`docs/evidence/aegis-temperature-calibration-admission-v1.json`](evidence/aegis-temperature-calibration-admission-v1.json),
file SHA-256
`18812f7dadaac52f80a9fcb34e15c2ad358540b834f6536e52e5a0e141608b4b`.

## Prior-Art Field Report

Actual source documentation and license files were inspected on 2026-10-16.

| Candidate | Capability and lesson | Maturity, tests, and maintenance | Platform, dependency, security, and license fit | Build versus adopt |
| --- | --- | --- | --- | --- |
| [OpenSSH SSHSIG protocol](https://github.com/openssh/openssh-portable/blob/master/PROTOCOL.sshsig) and [negative regressions](https://github.com/openssh/openssh-portable/blob/master/regress/sshsig.sh) | Detached signatures with an interpretation namespace and allowed-signers trust root | Mature, actively maintained, extensive positive and negative regression coverage | Already installed; offline; no service or Python crypto package. ISC-style OpenSSH terms; no code copied | **Adopt the installed verifier** behind TruePanel's existing narrow interface. A new namespace is the legitimate shortcut that prevents the field-review signature from approving labels. |
| [OpenLineage](https://github.com/OpenLineage/OpenLineage) | Run, job, and dataset identity plus extensible facets provide a clean vocabulary for recording-to-corpus lineage | LF AI & Data graduate project, active CI and integrations across major data systems | Full collectors/backends are far heavier than a local four-frame appliance workflow; Apache-2.0 | **Adapt the lineage idea**: bind source receipt, dataset identity, and case metadata in one record. No package or schema copied. |
| [MLCommons Croissant](https://github.com/mlcommons/croissant) | Dataset metadata, resources, structure, ML semantics, and file SHA-256 belong together | Community standard with CI, verifier, examples, and integrations in Kaggle, Hugging Face, OpenML, and TFDS | JSON-LD and `mlcroissant` would add schema and dependency weight before TruePanel publishes datasets; Apache-2.0 | **Adapt the resource-digest and responsible-metadata concepts**. Revisit export compatibility if a corpus is shared outside TruePanel. |
| [DVC](https://github.com/treeverse/dvc) | Content versioning, dependency/output graphs, local experiment comparison, and reproducibility | Mature, widely used, active CI and broad storage support | Core and remote plugins are disproportionate for a tiny bounded local corpus and would widen storage credentials/surface; Apache-2.0 | **Adapt content-addressed lineage**, not the runtime. Existing TruePanel digests and HANGAR evidence provide the needed subset. |
| [TensorFlow Data Validation](https://github.com/tensorflow/data-validation) | Schema generation, statistics, missing/out-of-range/type anomaly detection, and train/test comparison | Mature TFX component with releases and CI | Requires TensorFlow, Apache Beam, Arrow, and related packages; unsupported target assumptions and excessive appliance weight; Apache-2.0 | **Reject for this increment**. Benchmark its anomaly vocabulary later if the field corpus grows enough to justify a separate analysis environment. |

No third-party code, schema, service, credential, key, dataset, or dependency was
added. OpenSSH executable behavior was already isolated behind a TruePanel-owned
interface; only architectural concepts were adapted. The strongest
collaboration opportunity is OpenLineage: its maintainers could advise whether
TruePanel's compact receipt-to-corpus lineage should map to standard dataset
facets if evidence is ever exported.

## Failed approaches and challenged assumptions

- A field-review signature cannot authenticate labels that were not in its
  signed statement; treating it as sufficient would create a semantic replay.
- A new namespace without the same protected roster is insufficient; the
  evaluator pins both namespace and exact Ed25519 fingerprint.
- Caller booleans for `expected_shared_cooling` are useful proposal inputs, not
  trustworthy labels. The exact value now requires its own signature.
- Importing during verification would combine authentication with mutation and
  complicate safe retries. Admission remains a portable, read-only eligibility
  result; the existing corpus intake now rejects a repeated recording digest,
  while consumption of the authenticated admission remains deliberately
  separate.
- DVC, OpenLineage collectors, Croissant libraries, and TFDV could all model
  more, but their dependency and service weight does not buy stronger trust for
  one bounded local case.

## Open risks and next step

The successful path is fixture proof. No real JT roster, signature, or field
recording exists, and an authenticated admission is not yet a corpus entry.
After JT provisions the protected development public roster, the safe sequence
is: authenticate the development candidate, sign the field-review statement,
inspect and sign the exact label-bound admission statement, then run a separate
deduplicating import that preserves this receipt. Field validation, candidate
installation, and deployment remain later manual decisions.
