# AEGIS label-blind detector-result binding

## Outcome

This increment closes a calibration leakage gap: the detector now produces a
content-addressed prediction from the exact Black Box recording before an
operator's outcome labels are admitted. A distinct offline SSHSIG then binds
the prior signed admission, the immutable prediction, the detector contract,
and the recording identity. Success means only
`DETECTOR_RESULT_BOUND_FOR_CALIBRATION_REVIEW`.

It does not score the detector, validate field performance, accept or install a
candidate, deploy software, write to a corpus, or authorize hardware.

## Architecture

1. Read one protected, sanitized Black Box JSONL recording without labels.
2. Replay it through ORACLE and the existing replaceable AEGIS correlation
   boundary.
3. Preserve the first shared-cooling match, supporting evidence, confidence,
   detector ID, detector-contract digest, and exact recording bounds.
4. Rebuild the result during binding; reject changed recording, result, policy,
   timestamps, trust roots, namespaces, or authority fields.
5. Require the result timestamp to precede the signed admission timestamp.
6. Sign the exact binding under a new namespace. TruePanel only exports public
   material and verifies the detached return.

The deterministic fan-bearing fixture is detected at sample 19, 27 samples
before the first isolated threshold at sample 46. This repeats an existing lab
measurement; it is not a field-performance estimate.

## Prior-art field report

Research was refreshed on 2026-10-19 and inspected project documentation,
repository code/specifications, licensing, and current repository activity.

| Candidate | What it supplies | Maturity / maintenance / tests | Fit, weight, security | License / obligations | Recommendation |
|---|---|---|---|---|---|
| [Feast point-in-time joins](https://docs.feast.dev/getting-started/concepts/point-in-time-joins) and [source repository](https://github.com/feast-dev/feast) | Point-in-time correctness that prevents future values from leaking into historical training rows | Mature, actively maintained, extensive provider and join tests | Excellent semantic match; full feature-store dependency is far too heavy for a local NAS reliability engine | Apache-2.0; notices required if code is copied | **Adapt the invariant, not the package.** Prediction evidence must exist before labels. This is the strongest collaboration opportunity; Feast maintainers understand temporal leakage and training/serving skew. |
| [MLflow dataset tracking](https://mlflow.org/docs/latest/ml/dataset/) and [evaluation](https://mlflow.org/docs/latest/ml/evaluation/) | Dataset/model lineage, digests, predictions, metrics, and evaluation records | Very mature and active, broad test surface | Strong future backend for large studies; current dependency and service surface are disproportionate | Apache-2.0; preserve license/notice for copied code | **Defer adoption.** Reuse the lineage vocabulary; keep TruePanel's stdlib result envelope replaceable. |
| [Evidently](https://github.com/evidentlyai/evidently) | Offline and live evaluation, custom metrics, drift and data-quality reports | Active, modular, substantial tests and documentation | Promising future evaluator after a real corpus exists; Python/dataframe dependency weight is currently unnecessary | Apache-2.0 | **Evaluate later.** Do not calculate impressive metrics from four cases. |
| [OpenLineage specification](https://github.com/OpenLineage/OpenLineage/blob/main/spec/OpenLineage.md) | Extensible run/dataset lineage plus quality-metric and assertion facets | LF AI & Data graduate project, active multi-language implementations | Good schema inspiration; running an event service adds no value to this offline gate | Apache-2.0 | **Adapt facet semantics only.** Bind input recording, run contract, output result, and assertion state explicitly. |

No third-party code, schema, package, binary, service, credential, key, or
dataset was incorporated. The implementation uses TruePanel-owned JSON
contracts and its existing OpenSSH verifier. Apache-2.0 ideas were studied, so
there is no new attribution file or runtime obligation.

## Rejected and failed paths

- **Score after labels are loaded:** rejected because a detector or evaluator
  can accidentally consume ground truth and make the result circular.
- **Trust a result digest without replay:** rejected because a self-consistent
  but substituted policy/result pair can still be wrong.
- **Reuse the admission namespace:** rejected because admission and prediction
  binding are different semantic actions.
- **Install MLflow, Feast, Evidently, or OpenLineage now:** rejected because the
  current problem needs a small deterministic envelope, not a feature store,
  evaluation platform, dataframe stack, or lineage service.
- **Treat the existing four-frame temperature-recovery recording as a
  shared-cooling calibration window:** rejected. ORACLE correlation needs a
  longer baseline and drift sequence. The result runner accepts bounded longer
  recordings, but the existing field intake remains a separate four-frame
  recovery checkride.

## HoloDeck evidence

TP-EXP-0034 preserves ten scenarios: one bound result and nine HOLD outcomes.
HOLD covers post-label prediction, result tampering, recording drift, detector
contract substitution, label leakage, admission-signature tampering, namespace
substitution, binding-signature tampering, and authority escalation.

The passing case records a shared-cause detection at sample 19, the first
isolated threshold at sample 46, and a 27-sample lead. Unsafe-ready outcomes,
label inputs accepted by the detector, corpus writes, field validations,
candidate acceptance/installations, deployments, hardware actions, and runtime
writes are all zero.

## Open risks and next gate

The proof uses deterministic synthetic evidence. The replay code is structurally
label-blind, but its UTC ordering remains an operator-signed assertion rather
than an external trusted timestamp; it prevents accidental dataflow leakage, not
a dishonest operator from backdating an artifact. A real checkride needs a new,
explicitly governed long-window Black Box intake; the four-frame temperature
recovery intake must not be silently repurposed. Before computing sensitivity,
specificity, lead time, or uncertainty, predeclare the statistical gates and
minimum corpus size, then require every case to carry this exact result binding.
