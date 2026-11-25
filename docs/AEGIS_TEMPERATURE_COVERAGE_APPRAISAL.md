# AEGIS temperature coverage appraisal

Reviewed: 2026-10-09

## Decision

The ninth Recovery Coverage Matrix row is now **appraised, not accepted**.
The appraisal independently reconstructs the exact candidate from the accepted
8/8 matrix and the reviewed HoloDeck rehearsal, validates both self-digests,
and pins the complete candidate, evidence, predecessor, and implementation
subjects. Success reaches only `READY_FOR_INDEPENDENT_REVIEW`.

No candidate can accept or install itself. The accepted runtime matrix remains
8/8 trusted with zero gaps; the 9/9 candidate remains unaccepted, uninstalled,
and unable to authorize production, runtime, storage, network, or hardware
actions.

## Architecture and proof

The evaluator binds six exact SHA-256 subjects:

1. accepted matrix document;
2. candidate's declared digest;
3. complete candidate document;
4. HoloDeck report's declared evidence digest;
5. complete HoloDeck report; and
6. the candidate builder, validator, and checkride implementation source.

It then reconstructs the candidate rather than trusting the candidate's own
counts or digest. Ten deterministic cases produce one review-ready result and
nine `HOLD` results. The negative cases cover a self-consistent candidate
rewrite, predecessor drift, a self-consistent evidence rewrite, valid-shaped
evidence substitution, candidate self-acceptance, candidate self-installation,
an unknown candidate field, an unknown pin field, and evaluator drift. Unsafe
review-ready outcomes, acceptances, installations, writes, and hardware actions
remain zero.

Mission Control adds a mobile-safe Candidate Appraisal panel showing the exact
subject status and the `NO` authority boundaries beside the already separate
9/9 candidate. It does not relabel the accepted 8/8 matrix.

## Prior-art field report

Actual specification and implementation documentation was inspected on
2026-10-09 rather than relying on project descriptions alone.

| Candidate | What it supplies or teaches | Maturity and tests | Fit / dependency / security | License and attribution | Recommendation and likely saving |
| --- | --- | --- | --- | --- | --- |
| [in-toto Statement v1](https://github.com/in-toto/attestation/blob/main/spec/v1/statement.md) | Immutable subjects identified by digests, with the appraisal claim separated into a typed predicate | Versioned specification (latest framework spec reports v1.2); multiple language implementations | Excellent semantic fit; adopting an implementation would add envelope/signature concepts not needed at this gate | Apache-2.0 repository; preserve notices if code is later used | **Adapt the subject/predicate idea only.** Saved the design pass for a bespoke evidence-binding vocabulary |
| [SLSA Verification Summary Attestation](https://slsa.dev/verification_summary) | Verification result is separate from the artifact and policy that were evaluated | Approved specification with explicit parsing and verification rules | Strong appraisal/result model; SLSA levels themselves do not describe NAS recovery coverage | Community specification; no code incorporated | **Adapt result separation only.** Avoid implying that READY equals acceptance |
| [Prometheus promtool rule tests](https://github.com/prometheus/prometheus/blob/main/docs/configuration/unit_testing_rules.md) | Deterministic time-series inputs include explicit missing (`_`) and stale samples, with alert and expression expectations at evaluation times | Actively maintained production project with a large regression suite and stable CLI | Closest monitoring fit, Apache-2.0, but importing PromQL/Go tooling would add a heavy parallel rule engine | Apache-2.0; copyright and license notices required for copied code | **Adapt the deterministic missing-sample test pattern.** Keep TruePanel's existing Python simulator; likely avoids weeks of Prometheus embedding work |
| [The Update Framework](https://theupdateframework.github.io/specification/latest/) | Detect rollback, freeze, mix-and-match, and wrong-subject states before consuming an update | Mature security specification with multiple production implementations and conformance tests | Excellent fail-closed predecessor/substitution model; update metadata and key roles are out of scope here | Specification and implementations have their own permissive licenses; none copied | **Adapt exact-predecessor and mix-and-match rejection.** Do not import an update framework for an appraisal record |
| [Open Policy Agent](https://github.com/open-policy-agent/opa) | Replaceable declarative policy evaluation with unit-testable decisions | CNCF graduated, active, broad production adoption, extensive tests | Capable but disproportionately heavy for one small closed-schema evaluator; a separate binary/service expands attack and operational surface | Apache-2.0; notices required if distributed | **Do not adopt yet.** Revisit when several independent appraisal policies need shared policy distribution |

### Reusable code versus adapted ideas

No third-party source, schema, package, service, executable, credential, or key
was added. TruePanel owns the small appraisal interface and can replace it.
The increment adapts only immutable-subject binding, verification-summary
separation, deterministic missing-sample testing, and mix-and-match rejection.

### Rejected and failed paths

- Trusting `candidate_sha256` alone failed because an attacker can alter the
  candidate and recompute its self-digest.
- Trusting only the evidence's internal digest failed for the same reason.
- Checking counts such as `9/9` without reconstructing the candidate permits
  evidence substitution and semantic drift.
- Reusing the candidate's `READY_FOR_OPERATOR_REVIEW` label as acceptance would
  collapse appraisal, review, and installation into one unsafe state.
- OPA and a full in-toto/SLSA implementation were rejected for this increment:
  their extra runtime, schema, and trust-root surface saves less verified work
  than the small TruePanel-owned evaluator.

The most promising collaboration opportunity is the Prometheus rule-testing
community: its explicit missing/stale input semantics and time-indexed alert
expectations map directly to AEGIS observability faults. The in-toto attestation
maintainers are the best secondary contact for reviewing subject-binding and
appraisal-result semantics. Contacting either project remains JT's decision;
no external communication occurred.

## Open risks and next gate

- The appraisal is deterministic evidence, not authentication of a reviewer.
- The expected-member inventory has not been calibrated against a governed
  live read-only field sample.
- Source-text binding is intentionally strict; harmless implementation edits
  require a fresh appraisal rather than silent reuse.
- This increment depends on the exact PR #202 head and must not be
  reviewed or merged independently.

The next safe step is independent review of the exact appraisal and its
9/9 candidate. Only after that should a separately named successor consider a
manual development-only acceptance record. Installation and deployment remain
different, explicitly forbidden gates.
