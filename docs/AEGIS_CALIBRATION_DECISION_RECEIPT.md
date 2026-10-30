# AEGIS Calibration Decision Receipt

## Outcome

This increment adds a separately scoped, operator-authenticated **ACCEPT or
HOLD** decision over one exact independent calibration-score review. It does
not reinterpret the review as authority. `ACCEPT` reaches only
`ELIGIBLE_FOR_CALIBRATION_CANDIDATE_REVIEW`; `HOLD` is a durable operator
decision. Neither result can validate, install, deploy, promote automatically,
write runtime state, or actuate hardware.

The implementation is stacked on draft PR #230 and therefore depends on its
complete predecessor chain through frozen PR #78. PR #78 and
`feature/project-aegis` are unchanged.

## Contract

The SSHSIG statement binds the exact independent-review, score, statistical
contract, blinded manifest, detector contract, decision, rationale, protected
JT development key fingerprint, two-hour signing window, and every negative
authority claim. A distinct namespace prevents an older label, admission, or
development-review signature from being replayed as this decision.

Only a passing, independently reconstructed score may use
`ACCEPT_FOR_CALIBRATION_CANDIDATE_REVIEW`. A passing score may still be held.
A failing score must use `HOLD_CALIBRATION_CANDIDATE` with the explicit
`score-failed-statistical-gates` rationale. The decision registry is
owner-protected and content-addressed by review digest; a second decision for
the same review fails closed.

## HoloDeck evidence

TP-EXP-0041 covers 17 deterministic scenarios: three public statements ready
for offline signature, two candidate-review-eligible ACCEPT results (the
primary path and a separate replay fixture), two recorded operator HOLDs, and
ten adversarial HOLD results. The semantic proof is one passing ACCEPT, one
passing HOLD, one failing HOLD, and zero failing ACCEPTs.

The same 440-case fixture retains 40 positive and 400 negative cases. Shared
cooling is identified at sample 19, the first isolated threshold at sample 46,
and AEGIS therefore retains its 27-sample lead. Score-registry writes,
validation, candidate acceptance, installation, deployment, automatic
promotion, hardware action, and production writes remain zero.

Preserved evidence:
`docs/evidence/aegis-temperature-calibration-decision-v1.json`.

## Prior-Art Field Report

Research was refreshed on 2026-10-26 and inspected the projects' actual
documentation, source, tests where relevant, and license files.

| Candidate | Useful capability | Maturity / test signal | Platform fit and weight | Security / license | Recommendation |
| --- | --- | --- | --- | --- | --- |
| [in-toto Attestation](https://github.com/in-toto/attestation) | Authenticated subjects plus a documented policy-decision example that binds evidence and a policy digest | Active specification and generated bindings; policy-decision predicate is illustrative rather than an AEGIS-ready stable predicate | Strong semantic fit; adopting its full envelope and bindings is unnecessary for one offline receipt | Apache-2.0; attribution and license notice required if code is copied | **Adapt concepts.** Bind exact subjects, policy evidence, result, and validity window. Do not copy schema or code. |
| [SLSA VSA](https://slsa.dev/spec/v1.2/verification_summary) | Separates verification evidence, policy, and PASSED/FAILED result | Versioned specification used by supply-chain verifiers | Excellent model for the independent score review; intentionally not a human operator-decision format | Specification terms are permissive; no code adopted | **Adapt concepts.** Keep review evidence distinct from the operator decision. |
| [OPA decision logs](https://www.openpolicyagent.org/docs/management-decision-logs) | Auditable decision ID, exact query input/result, bundle revision, and masking | Mature CNCF project with extensive implementation and tests | Excellent audit vocabulary, but OPA/Rego plus log shipping is excessive for an offline single-user gate | Apache-2.0; logs can leak sensitive input unless masked | **Adapt concepts.** Preserve decision identity and policy revision; reject runtime dependency and remote log service. |
| [Cedar](https://github.com/cedar-policy/cedar) | Explicit allow/deny response with diagnostics and determining policies | Mature, security-focused Rust engine with differential and integration testing | Useful future policy engine, but Rust/library integration is disproportionate to two fixed choices | Apache-2.0; policy inputs still need authenticated provenance | **Defer adoption.** Revisit if AEGIS develops many principals, resources, and policy versions. |
| OpenSSH SSHSIG | Detached signature with an application namespace and allowed-signers trust root | Already installed, exercised by upstream regression tests, and used throughout AEGIS | Exact fit with no new Python dependency or external service | Permissive OpenSSH license; public roster only, private key remains external | **Adopt behind TruePanel's interface.** This remains the only external implementation used here. |

### What was incorporated

Only architectural semantics were adapted: in-toto subject binding, SLSA's
evidence-versus-decision separation, OPA's decision/policy revision linkage,
and Cedar's explicit allow/deny vocabulary. The installed OpenSSH verifier is
invoked behind `OpenSshSignatureVerifier`. No third-party code, schema,
package, service, credential, key, dataset, generated binding, or remote policy
engine was added.

### Rejected candidates and failed approaches

- Treating `statistical_gates_passed` as automatic approval was rejected: a
  reconstructed metric result is evidence, not an operator decision.
- Allowing ACCEPT on a failing score was rejected even when signed; operator
  identity cannot override the predeclared statistical contract silently.
- Reusing the label-signing namespace was rejected because a valid old
  signature could acquire a new meaning.
- A mutable “current decision” file was rejected because it permits replacement
  and obscures prior intent. The review digest now names an exclusive receipt.
- OPA and Cedar runtime dependencies were rejected for this narrow two-choice
  gate. Their policy and audit ideas save design time, but their binaries,
  language runtimes, distribution, and update surfaces do not yet save verified
  implementation time.
- Remote transparency logs were not simulated. POSIX content custody is not
  equivalent to independently witnessed publication.

### Collaboration opportunity

The in-toto Attestation maintainers are the strongest collaboration target.
AEGIS now has adjacent, concrete examples of an evaluation-result predicate
and a human decision receipt with a strict non-operational scope. A future
standard predicate could prevent each reliability project from inventing its
own evidence-to-decision handoff. No maintainer was contacted.

## Open risks and next gate

- No real JT signature, governed field cohort, label set, score, review, or
  decision exists yet.
- The verifier and producer still share a Python distribution even though the
  review implementation is separate.
- The receipt store is local POSIX custody, not a distributed transparency log.
- Candidate-review eligibility is not field validation and says nothing about
  safe installation.

The strongest next step is a separate, read-only candidate dossier that joins
the accepted decision, score review, sealed score, detector contract, Recovery
Coverage Matrix, and HoloDeck evidence for human inspection. It must not install
or deploy the candidate and must preserve HOLD as a terminal outcome.
