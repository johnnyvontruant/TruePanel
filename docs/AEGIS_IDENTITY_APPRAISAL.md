# AEGIS identity-coverage appraisal

Status: deterministic lab proof only. The accepted Recovery Coverage Matrix v1
remains unchanged. The identity-aware v2 matrix remains an unaccepted candidate.

## Outcome

The appraisal gate answers one narrow question: does the exact v2 candidate
still match the accepted predecessor, its deterministic identity evidence, a
reviewed appraisal policy, and the evaluator implementation? A complete match
reaches `READY_FOR_INDEPENDENT_REVIEW`; it never reaches accepted, installed,
or deployable state.

The policy binds:

- the semantic SHA-256 of accepted matrix v1;
- the complete v2 candidate, including its no-auto-acceptance boundary;
- the identity-continuity rehearsal and zero-false-outcome measurement;
- the appraisal implementation itself; and
- the exact candidate schema and expected pre-review status.

Mission Control now reports the appraisal beside the candidate and explicitly
shows that independent review is incomplete and the candidate is not accepted.
The accepted 8/8 matrix and current AIRWORTHINESS decision are not changed.

## HoloDeck evidence

`docs/evidence/aegis-identity-appraisal-v1.json` preserves six deterministic
cases: one exact candidate becomes review-ready; predecessor drift, an unknown
candidate field, identity-evidence drift, evaluator drift, and candidate
self-promotion all produce `HOLD`. There are zero false-ready results, candidate
acceptances, runtime writes, or production writes.

## Prior-art field report

Research and repository inspection were refreshed on 2026-09-16. Repository
activity dates below are GitHub `pushed_at` observations from that date.

| Candidate | Useful capability | Maturity / activity | Fit and dependency weight | License / obligations | Recommendation |
| --- | --- | --- | --- | --- | --- |
| [in-toto Attestation Statement](https://github.com/in-toto/attestation/blob/main/spec/v1/statement.md) | Binds an immutable subject digest to a typed predicate; its resource descriptor also makes digest-to-resource semantics explicit. | Active; pushed 2026-09-14; published v1 spec and named maintainers. | Excellent semantic fit; no runtime dependency needed. | Apache-2.0. Attribution required only if code/spec text is copied. | Adapt subject/digest separation, retain a TruePanel-owned schema. |
| [SLSA Verification Summary Attestation](https://github.com/slsa-framework/slsa/blob/main/spec/verification_summary.md) | Binds verifier identity, policy digest, input-attestation digests, and a pass/fail result. | Active; pushed 2026-09-11; specification includes a current v1.2 change history. | Strongest shortcut for the appraisal result model; adopting its full signed envelope now would duplicate TruePanel's existing offline review layer. | Community Specification License 1.0; implementations need no attribution, derivative specification text does. | Adapt policy and input-evidence bindings; do not import a library or claim SLSA conformance. |
| [IETF RATS architecture, RFC 9334](https://www.rfc-editor.org/rfc/rfc9334.html) | Cleanly separates Evidence, appraisal policy, Verifier, Attestation Results, and the Relying Party's final trust decision. | IETF Proposed Standard, published January 2023. | Excellent architectural fit and prevents appraisal from being confused with acceptance. No dependency. | IETF Trust terms; extracted code components use Revised BSD terms. | Adapt the role separation and vocabulary only. |
| [TUF specification](https://github.com/theupdateframework/specification/blob/master/tuf-spec.md) | Protects predecessor metadata, freshness, mix-and-match, rollback, and threshold transitions. | Active; pushed 2026-09-14; spec source reports version 1.0.36 dated 2026-08-05. | Valuable for later signed acceptance and succession. Full TUF adoption is too heavy for a local coverage candidate. | Community Specification License 1.0. | Reuse transition principles in the existing review stack, not in this appraisal evaluator. |

The implementation adapts semantics rather than code. It adds no dependency,
network service, credential, key, third-party schema, or notice-bearing artifact.
All behavior remains behind TruePanel-owned Python and JSON interfaces with
tests, so the policy mechanism can be replaced later.

### Rejected approaches

- Treating a valid SHA-256 as reviewer authentication: integrity is not
  authenticity, so appraisal remains explicitly incomplete until independent
  review.
- Accepting unknown candidate fields for forward compatibility: this is an
  acceptance-boundary gate, so an extension requires a new reviewed policy.
- Trusting only the candidate's self-declared digest: the policy independently
  names the expected candidate and evidence digests.
- Replaying only the happy path: every binding has an adversarial HoloDeck case.
- Vendoring an attestation or TUF implementation: it would add unnecessary
  dependency and key-management surface without completing operator review.
- Updating the accepted matrix or assurance envelope in the same increment:
  that would collapse appraisal and acceptance into one authority domain.

### Collaboration opportunity

The strongest prospective collaboration target is the in-toto Attestation and
SLSA VSA maintainer community, especially the current in-toto Attestation
maintainers listed in its repository. Their feedback could help decide whether
a future externally signed TruePanel appraisal should use a standard predicate.
No maintainer was contacted and no external post was made.

## Open risks and next gate

The appraisal policy is content-bound but unsigned. It is strong deterministic
review material, not independent approval. PR #155 must remain separate and be
reviewed first. The next safe step is for two operator-owned reviewers to sign
the exact appraisal/candidate bundle through the existing offline review
boundary, then construct a successor AIRWORTHINESS envelope that still requires
manual promotion. No live observation or deployment is justified by this proof.
