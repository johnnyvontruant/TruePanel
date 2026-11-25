# AEGIS Predeclared Statistical Calibration Contract

## Outcome

AEGIS now has a fixed statistical policy before any authenticated outcome labels are
available. The policy is content-addressed, tied to the receipt-bound detector-result
schema, and independently reconstructable. It defines not only metric names but the
cohort floors, confidence method, denominators, lead-time population, abstention
treatment, and anti-tuning rules required for one future independent score.

The predeclared state authorizes blinded cohort collection only. It does not mean a
cohort exists, does not accept scores, and grants no field validation, candidate
acceptance, installation, deployment, storage, network, or hardware authority. The
accepted Recovery Coverage Matrix remains 8/8 trusted with zero gaps.

## Fixed policy

- At least 40 positive and 400 negative authenticated cases (440 total).
- At least two system profiles, four workload classes, and 20 positive cases with an
  isolated-threshold landmark.
- Two-sided 95% Wilson intervals.
- Sensitivity Wilson lower bound at least 0.80.
- False-positive-rate Wilson upper bound at most 0.01.
- Abstention-rate Wilson upper bound at most 0.01; abstention is never counted as a
  negative prediction.
- Median lead at least 12 samples and p10 lead at least 4 samples, measured only over
  true-positive cases that have an isolated-threshold landmark.
- An immutable cohort manifest must be frozen before labels are revealed.
- One evaluation per detector contract; no post-label threshold tuning, selective case
  exclusion, or automatic promotion.

The feasibility proof is deliberately conservative: at the cohort floors, a perfect
40/40 positive result has a 0.912378 sensitivity lower bound, zero false positives in
400 negatives has a 0.009512 upper bound, and zero abstentions in 440 cases has a
0.008655 upper bound. The policy can therefore pass without weakening itself.

## HoloDeck evidence

TP-EXP-0037 preserves ten deterministic paths: one exact predeclared policy and nine
HOLD outcomes. Relaxed positive/negative floors, sensitivity, false-positive bounds,
missing lead-time criteria, post-label tuning, outcome injection, unknown fields, and
authority escalation all fail closed.

Evidence: `docs/evidence/aegis-temperature-statistical-calibration-contract-v1.json`
(file SHA-256 `e92f9b594ee808b3a8ff5f730ac58ef9f300d4d2b973c07d84004f4836a71896`;
embedded evidence SHA-256 `a18aaf3970d205890af384eaf195a4b2697daa9db71b80b067dea52db98099bd`).

Labels accepted, scores accepted, field validations, candidate acceptances,
installations, deployments, hardware actions, and runtime writes are all zero.

## Prior-Art Field Report

| Candidate | Capability and lesson | Maturity / fit | Dependency and security | License / attribution | Recommendation |
|---|---|---|---|---|---|
| [scikit-learn model evaluation](https://scikit-learn.org/stable/modules/model_evaluation.html) | Standard confusion-matrix, sensitivity/recall, precision and support semantics | Mature, extensively tested, but a large dependency for fixed arithmetic | Adding NumPy/SciPy/scikit-learn would expand the supply chain and installed footprint | BSD-3-Clause; attribution required if code is incorporated | **Adapt metric semantics only**; standard-library evaluation is sufficient |
| [NIST proportion confidence intervals](https://www.itl.nist.gov/div898/handbook/prc/section2/prc241.htm) | Recommends Wilson intervals over fragile normal approximations for binomial proportions | Authoritative statistical guidance; directly fits small-error-rate gates | No runtime dependency; the repository already owns and tests its Wilson implementation | U.S. government publication; cite NIST guidance | **Adopt the method through existing TruePanel code** |
| [MLCommons benchmark process](https://mlcommons.org/benchmarks/) | Predeclared requirements, reproducibility, compliance runs and independent review | Mature benchmark governance; useful process model, not a telemetry library | Full submission tooling is disproportionate and would not establish TruePanel field validity | MLCommons materials and code have project-specific terms; no code copied | **Adapt locked-rule and reproducibility concepts** |
| [Evidently](https://github.com/evidentlyai/evidently) | Broad evaluation, drift, testing and report framework | Active, tested and capable; attractive once a real multi-case corpus exists | Heavy dataframe/analytics dependency and optional service surface exceed this contract’s needs | Apache-2.0; preserve license and notices if later adopted | **Revisit for replaceable report generation**, not policy authority |

No external code, schema, package, service, credential, key, or dataset was added. The
new module reuses TruePanel’s existing tested Wilson primitive behind a TruePanel-owned
contract. scikit-learn and Evidently were rejected as runtime dependencies because the
current task is policy fixation, not general analytics. MLCommons submission machinery
was rejected because compliance with its benchmark process would not validate NAS
cooling diagnosis.

The strongest collaboration opportunity is NIST statistical-methods maintainers or
reviewers for validating the interval and sample-floor interpretation; Evidently is the
best future implementation partner if corpus-scale reporting becomes worth its
dependency cost. External contact remains out of scope.

## Failed assumptions and open risks

- Naming sensitivity and specificity does not prevent biased denominators.
- Point estimates do not establish conservative error-rate bounds.
- A mean lead time can hide late detections; the median and p10 are both required.
- Abstentions cannot safely be counted as correct negatives.
- A passing fixture proves the policy implementation, not field performance.
- The 440-case floor is a predeclared engineering policy, not a universal scientific
  truth; changing it requires a new version before examining the affected labels.
- No real JT signature, governed field cohort, or independent score exists.

## Next gate

Create a content-addressed blinded cohort manifest that binds every authenticated
intake-bound detector result before exposing any outcome labels. Only after that freeze
may a separate scorer join results to authenticated admissions and evaluate this exact
contract once.
