# AEGIS Temperature Calibration Corpus Assessment

## Outcome

This increment adds a read-only assessment boundary after authenticated corpus
import. Every case must preserve its detached admission SSHSIG; assessment
replays that signature, recording and statement lineage, then applies explicit
case-count, outcome-balance, system-profile, workload and threshold-landmark
gates. Success means only
`CALIBRATION_CORPUS_CHARACTERIZED_FOR_INDEPENDENT_REVIEW`.

It does not estimate field accuracy, validate a detector, accept or install the
9/9 temperature candidate, deploy software, or grant runtime or hardware
authority. The accepted Recovery Coverage Matrix remains 8/8 trusted.

## Trust gap closed

The first append-only importer retained the admission statement and an
unsigned receipt, but not the detached signature that authenticated the
statement. A later reader could check integrity but could not independently
replay operator authentication. New imports therefore preserve the public
SSHSIG, bind its digest and byte count into the import receipt, and require the
assessment reader to verify it against the exact protected admission roster.

The assessment takes a shared corpus lock, scans and validates the corpus
twice, authenticates every statement, cross-checks statement labels and
recording bounds against the receipt, rejects authority escalation, and emits
one deterministic corpus snapshot digest. It performs no corpus write.

## Prior-Art Field Report

| Candidate | Actual capability inspected | Maturity / tests | Fit and dependency weight | License / obligation | Recommendation |
|---|---|---|---|---|---|
| TensorFlow Data Validation | Schema-driven statistics validation, environment-aware validation, drift and skew comparators, anomaly reports | Mature TFX component with direct `validate_statistics` tests and a June 2026 release adding quantile histogram selection | Strong model for explicit dataset gates, but TensorFlow, Beam, Arrow and metadata dependencies are disproportionate for four-frame local cases | Apache-2.0; preserve notices if code is copied | Adapt the declarative gate and anomaly-report ideas only |
| Evidently | Data/model-quality metrics, test suites, reference/current comparisons and JSON reports | Active project with broad metric coverage and examples | Promising future benchmark/report adapter once a representative corpus exists; current pandas/plot/report surface is unnecessary for the secure intake boundary | Apache-2.0; preserve license and notices if distributed | Revisit behind a replaceable analysis interface after governed corpus growth |
| scikit-learn | Calibration curves, cross-validation and model-scoring contracts with extensive negative tests | Very mature, actively maintained and deeply tested | Best future shortcut for statistically meaningful detector comparison; NumPy/SciPy stack is too heavy before there is enough data to justify a model benchmark | BSD-3-Clause; retain copyright, license and disclaimer; no endorsement | Collaboration target for future replaceable benchmark, not this gate |
| Great Expectations | Expectation suites, validation results and checkpoint-driven data tests | Mature data-quality ecosystem with validation-result documentation | Expressive, but its datasource, checkpoint, store and documentation machinery exceeds a private four-frame local corpus | Apache-2.0; preserve notices if code is copied | Architectural inspiration only |

No third-party code, schema, package, binary, service, credential, key or
dataset was incorporated. TruePanel uses standard-library POSIX primitives and
the already-adopted installed OpenSSH verifier behind TruePanel-owned
interfaces. The strongest collaboration opportunity is scikit-learn's model
evaluation community when the corpus reaches a predeclared diversity floor;
TFDV maintainers are the strongest source for dataset-gate design review.

## Rejected and failed approaches

- Treating a receipt digest as operator authentication. A hash protects
  integrity only; the detached SSHSIG must remain replayable.
- Calling four balanced fixture cases validation. They prove the assessment
  contract, not field performance or generalization.
- Adding TFDV, Evidently, scikit-learn or Great Expectations now. All are
  legally compatible, but their dependency and operational weight save no
  verified development time at the current corpus size.
- Computing accuracy from operator labels without an independently recorded
  detector prediction. That would be circular and misleading.
- Allowing corpus characterization to alter the corpus, accept the candidate,
  or lift any runtime gate.

## HoloDeck evidence

TP-EXP-0033 exercises nine deterministic paths: one balanced authenticated
corpus becomes review-ready and eight remain HOLD for insufficient cases,
outcome imbalance, profile collapse, signature tampering, lineage
substitution, signed authority escalation, recording drift, or verifier-policy
drift. The passing corpus contains four authenticated cases: two positive, two
negative, two profiles and two workloads. Corpus writes, validations,
acceptances, installations, deployments, hardware actions and runtime writes
remain zero.

## Limits and next step

The current gates characterize sufficiency; they do not compute sensitivity,
specificity, lead time, confidence calibration or uncertainty intervals because
no independent detector outputs exist in the admitted case schema. The next
safe step is to extend the admission contract with immutable detector-result
evidence, then assess predictions against operator labels with predeclared
uncertainty floors. A real run still requires JT's protected public roster and
offline signatures; no private key belongs in TruePanel.
