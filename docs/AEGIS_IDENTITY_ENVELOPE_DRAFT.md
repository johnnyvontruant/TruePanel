# AEGIS identity coverage successor envelope draft

## Outcome

This increment converts an *eligible* two-person identity-coverage review into
an expiring successor AIRWORTHINESS **draft**. It does not accept the Recovery
Coverage Matrix candidate, install the envelope, or authorize deployment. The
normal runtime has no signatures and therefore remains `HOLD` with no draft.

The draft binds the accepted predecessor envelope, accepted v1 matrix, complete
v2 candidate, appraisal, review packet and receipt, correlation policy, platform
version, and every existing runtime subject. Only the coverage subject is
replaced; the new evaluator and review modules are added as explicit subjects.
The existing successor-envelope evaluator then independently checks the result.

## Prior-art field report

The sources below were inspected at their specification or implementation
files, not only at project descriptions.

| Candidate | What it supplies | Maturity and maintenance | Platform fit / dependency weight | Security and test posture | License / obligation | Recommendation |
| --- | --- | --- | --- | --- | --- | --- |
| [TUF specification](https://github.com/theupdateframework/specification/blob/master/tuf-spec.md) | Successive trust-root updates must satisfy both the predecessor and successor thresholds; version and expiry resist rollback and freeze attacks. | Mature CNCF security specification with interoperable implementations. | Excellent semantic fit; no runtime dependency needed. | Explicit compromise, threshold, rollback, and expiry threat model. | Community Specification License 1.0 / CC-BY-4.0 for the specification; attribution applies to derivative specification text, not an implementation. | **Adapt the transition semantics.** Keep TruePanel's narrower envelope and independent manual boundary. |
| [Uptane standard](https://github.com/uptane/uptane-standard/blob/master/uptane-standard.md) | Separates assignment/decision authority from offline image truth and requires agreement across independently governed metadata. | Mature Linux Foundation automotive standard; repository is active and versioned. | Strong safety analogy, but a full Uptane deployment is far too heavy for a local NAS dashboard. | Designed for compromised networks, replay, rollback, and partial device capability. | Community Specification License 1.0 / CC-BY-4.0; implementation use is allowed under its terms. | **Adapt separation of duties only.** Do not import its services or wire protocols. |
| [in-toto Statement v1](https://github.com/in-toto/attestation/blob/main/spec/v1/statement.md) | Digest-addressed immutable subjects and an explicit predicate type cleanly separate what was reviewed from the review claim. | Widely used, actively maintained OpenSSF/CNCF-adjacent specification. | Excellent data-model fit; direct schema adoption would add compatibility surface without current benefit. | Clear subject matching; warns that digest matching alone does not establish content type or reviewer identity. | Apache-2.0. Notice and license obligations apply if code or schema text is copied. | **Adapt subject-binding semantics.** Retain TruePanel-owned strict schemas and SSHSIG identity checks. |
| [SLSA VSA](https://github.com/slsa-framework/slsa/blob/main/spec/verification_summary.md) | Binds a subject to verifier identity, policy digest, input attestations, time, and pass/fail result. | Active OpenSSF project with named workstreams and released specification branches. | Very close appraisal model, but SLSA levels and transitive build dependencies are not AEGIS recovery semantics. | Strong verifier/policy separation; its forward-compatible unknown-field rule is unsafe at this acceptance boundary. | Community Specification License 1.0 for current specification material; older portions may be Apache-2.0. | **Adapt verifier/policy/input separation.** Deliberately reject unknown fields instead of adopting VSA parsing rules. |
| [Sigstore Cosign](https://github.com/sigstore/cosign) | Standard signing bundles, identity-bound verification, transparency, and keyless workflows. | Highly active production ecosystem with broad test and platform coverage. | Potential future verifier adapter; current hosted identity/transparency assumptions add privacy and availability dependencies. | Strong ecosystem, but online trust roots and identity disclosure require an operator policy decision. | Apache-2.0; notices required if code is incorporated. | **Defer.** Existing OpenSSH verification remains offline, small, and replaceable. |

## Build-versus-adopt decision

Build the small TruePanel-owned draft constructor and reuse the already tested
successor-envelope evaluator. Adapt TUF's dual-sided transition, Uptane's
separation of assignment from artifact truth, and in-toto/SLSA subject-policy
binding. No external code, schema, service, dependency, key, credential, or
dataset is incorporated, so no new runtime notice is required.

A full TUF/Uptane metadata stack was rejected because it would introduce roles,
repositories, serialization, key-management, and update transport that AEGIS
does not need. Direct in-toto/VSA schema adoption was rejected because their
extension rules intentionally accept unknown fields, while this narrow
acceptance boundary must fail closed. Cosign was rejected for this increment
because operator identity, transparency, privacy, offline availability, and
trust-root policy remain unresolved.

The strongest collaboration opportunity is the TUF/Uptane maintainer community:
their experience with independently governed successive metadata can validate
whether TruePanel's final manual acceptance boundary misses a transition or
rollback class. Contacting maintainers is intentionally left to JT.

## HoloDeck result

`TP-EXP-0032` contains nine deterministic scenarios: one exact reviewed draft
reaches `READY_FOR_INDEPENDENT_ENVELOPE_REVIEW`, while unsigned review, reviewer
count spoofing, candidate tampering, appraisal tampering, coverage drift,
subject drift, automatic acceptance, and expiry all produce `HOLD`. The proof
created one lab draft and zero accepted envelopes, installed envelopes, false
ready outcomes, runtime writes, production writes, hardware actions, or
production keys.

The ZFS-member to WWN migration requested by the previous experiment is not
silently added here. It would change evidence already bound by the appraisal and
two-person review packet. That scenario requires a new candidate, appraisal,
and review cycle.

## Remaining gate

The repository contains no operator signatures. Runtime status therefore stays
`IndependentReviewRequired`. Two operator-owned signatures over the exact
packet are required before this draft can be reproduced. A separately reviewed
successor envelope could then become eligible for a later, manual acceptance
decision; deployment remains another independent operation.
