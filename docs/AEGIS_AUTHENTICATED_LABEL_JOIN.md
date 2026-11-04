# AEGIS authenticated label join and one-shot score receipt

## Result

This increment closes the boundary between the frozen, label-blind cohort and
statistical review. It authenticates one outcome for every member of the exact
cohort manifest, verifies the operator's detached OpenSSH SSHSIG, evaluates the
predeclared policy without exclusions or threshold changes, and atomically
publishes one immutable score receipt per detector contract.

Both passing and failing authenticated scores consume the evaluation. A failed
score cannot be relabeled, selectively filtered, or rerun until it passes. A
passing score reaches only `AUTHENTICATED_CALIBRATION_SCORE_REVIEW_READY`; it is
not field validation, candidate acceptance, installation, promotion, deployment,
or hardware authority.

## Trust boundary

- The statistical contract and blinded manifest are independently reconstructed.
- The label statement binds their digests, the detector contract, all 440 case
  identities and outcomes, the public-key fingerprint, the validity window, and
  every negative authority claim.
- The operator signature uses a distinct SSHSIG namespace. TruePanel accepts no
  private-key input and invokes no signer.
- Missing, extra, duplicate, changed, expired, unsigned, or differently signed
  labels fail closed.
- The score registry is an operator-owned, non-writable-by-group/others POSIX
  directory. A fully synced staging inode is linked atomically to the fixed
  detector-contract filename; an existing filename rejects every rescore.
- The receipt records the exact contract, manifest, label statement, detached
  signature, evaluator result, Wilson bounds, lead-time method, and negative
  authority claims.

## Deterministic HoloDeck proof

`TP-EXP-0039` exercises 13 paths: two public statements become signing-ready,
one authenticated cohort passes all gates, one authenticated weak cohort is
sealed with failing gates, and nine adversarial paths HOLD.

The passing fixture contains 40 positive and 400 negative cases. It reports:

- sensitivity Wilson lower bound: `0.912378`;
- false-positive-rate Wilson upper bound: `0.009512`;
- abstention-rate Wilson upper bound: `0.008655`;
- shared-cooling detection at sample 19 versus isolated threshold 46;
- median and nearest-rank p10 lead: 27 samples; and
- zero exclusions, threshold changes, repeat scores, validation claims,
  deployments, or hardware actions.

The fixture is a contract proof, not field evidence. No real JT key, signature,
label set, recording, or score has entered the system.

## Prior-Art Field Report

| Candidate | What it supplies | Maturity / maintenance / tests | Fit and dependency weight | License / attribution | Decision |
| --- | --- | --- | --- | --- | --- |
| [in-toto Test Result predicate](https://github.com/in-toto/attestation/blob/main/spec/predicates/test-result.md) | Exact subject plus test configuration and result semantics | Vetted predicate in the maintained in-toto attestation specification; language bindings and conformance work exist | Strong semantic fit, but adopting its full envelope and bindings would duplicate TruePanel's canonical records and SSHSIG boundary | Apache-2.0; retain notice if code is copied | Adapt subject/configuration/result separation only |
| [SLSA Verification Summary Attestation](https://slsa.dev/spec/v1.2/verification_summary) | Binds verifier, evidence bundle, policy, and verified subject | Maintained OpenSSF specification with a production Go verifier | Strong review-receipt model; generic supply-chain vocabulary is heavier than this offline statistical gate | Community Specification License 1.0 for newer spec content; some earlier content Apache-2.0 | Adapt verifier/bundle/policy binding; do not copy schema or code |
| [TUF specification](https://theupdateframework.github.io/specification/v1.0.36/) | Rollback/freeze resistance and monotonically trusted state | Widely deployed security standard with adversarial client tests | Its replace/rollback rule directly informs rejecting a second score; role/metadata machinery is otherwise disproportionate | Community Specification License 1.0 / CC-BY-4.0 license text | Adapt non-replacement semantics only |
| [MLCommons policies](https://github.com/mlcommons/policies) and [Inference rules](https://github.com/mlcommons/inference_policies/blob/master/inference_rules.adoc) | Fixed system/configuration, compliance gates, review, and unverified-result labeling | Active benchmark governance and large public submission ecosystem | Excellent governance precedent; full harnesses target performance benchmarking rather than NAS reliability calibration | Apache-2.0; MLPerf name is trademarked and has result-messaging obligations | Adapt fixed-config and independent-review concepts; do not claim an MLPerf result |
| OpenSSH SSHSIG | Detached signature with explicit namespace and public roster | Already installed, regression-tested, and wrapped by TruePanel | Best technical fit and zero new Python dependency; private key remains offline | OpenSSH license notices apply to OpenSSH itself; no code copied | Adopt installed verifier behind TruePanel interface |

No third-party code, schema, package, service, credential, key, or dataset was
incorporated. Only architectural semantics were adapted. The strongest
collaboration opportunity is the in-toto attestation maintainers: a future
generic statistical-test predicate could make score receipts interoperable
without importing a runtime framework.

## Rejected or failed approaches

- **Seal only passing scores:** rejected because weak labels could be changed and
  retried. Authenticated failures now consume the same one-shot gate.
- **Treat a deterministic receipt digest as one-shot enforcement:** rejected;
  different labels create a different digest. The fixed detector-contract
  registry entry is the non-replaceable commit point.
- **Write the final receipt directly:** rejected because readers could observe a
  partial file. The implementation syncs a staging inode and atomically links it.
- **Allow callers to omit inconvenient cases:** rejected. The signed label set
  must equal the exact frozen case set.
- **Use a point estimate alone:** rejected. Wilson bounds and the locked
  denominators decide the gates.
- **Use an interpolated percentile without naming it:** rejected. The receipt
  records `nearest-rank-ceiling` for p10.
- **Call a passing simulation field validation:** rejected. Every authority and
  validation field remains false.

## Open risks and next gate

- One-shot enforcement is scoped to one protected local POSIX registry. A
  distributed or replicated evaluator needs a consensus-backed equivalent.
- The operator-signed time window is not an external trusted timestamp.
- The deterministic cohort demonstrates the scoring contract, not real-world
  accuracy, chassis diversity, or workload coverage.
- A future independent score reviewer must reconstruct the committed receipt and
  evidence before any validation proposal. It must still be unable to accept,
  install, deploy, or actuate hardware.

The strongest next step is an independent score-review receipt that reconstructs
the exact committed passing or failing score and produces an appraisal only. It
must preserve the one-shot result and retain a separate manual gate for any
future field-validation claim.
