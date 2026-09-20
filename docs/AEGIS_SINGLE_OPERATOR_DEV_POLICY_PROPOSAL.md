# AEGIS single-operator development review: proposed policy

Status: DESIGN ONLY. Not implemented, accepted, installed, or deployed.

## Authority and identity

JT is the sole human accountable operator and sole authorized signer for this development-only policy. Vega is an AI-assisted reviewer and test operator, not a second human, independent signing identity, or source of approval authority. A model-produced review report is evidence, not a signature or an independent approval.

This policy is a separately named alternative to the existing two-human review policy; it does not satisfy, rewrite, downgrade, or automatically bypass any existing two-person requirement. Existing artifacts reviewed under the two-human policy remain HOLD until independently reappraised under an explicitly applicable policy. No historical receipt may be relabeled.

## Permitted result

A successful, manually confirmed operator signature may yield only `ELIGIBLE_FOR_DEVELOPMENT_CANDIDATE_REVIEW`. It must not produce `ELIGIBLE_FOR_MANUAL_ENVELOPE_ACCEPTANCE`, accepted coverage, accepted envelope, installed envelope, deployment authorization, or control authority.

Production deployment and live hardware/storage/network/fan/LCD/LED/boot-task actions remain separately gated and are out of scope. A single-operator development review must not be accepted by any existing production or deployment gate.

## Proposed deterministic contract (not yet implemented)

1. Bind the exact source commit, policy version and digest, candidate/evaluator hashes, complete HoloDeck evidence and coverage matrix, and the reviewer report to a canonical review packet.
2. Independently recompute all bound digests and rerun the evaluator and relevant regression fixtures. Treat reviewer prose and model-generated confidence as untrusted inputs.
3. Require one current operator-owned signature over the exact packet, with a bounded expiry and replay-resistant review identifier. Never create or store the private key in the repository, service, CI, or assistant context.
4. Fail closed for unknown fields, changed commit or evidence, expired/reused signatures, incomplete recovery guidance, missing verification/rehearsal, evaluator drift, or a claim that AI review is a second human signature.
5. Separate development-review output types and namespaces from two-human acceptance, installation, and deployment. A consumer must explicitly opt into the development-only type; it must not silently coerce to a stronger status.
6. Publish an audit record naming one human signer, AI-assisted review as supporting evidence, checks executed, limitations, and the exact no-deploy boundary.

## Required tests before implementation can be considered complete

- Valid single-operator development packet reaches only development-review eligibility.
- Missing/invalid/expired/replayed signature, stale code or evidence, evaluator substitution, unknown field, or missing HoloDeck rehearsal produces HOLD.
- A single operator with two keys never satisfies the two-human policy.
- No development-only receipt is accepted by the existing envelope-acceptance, installation, deployment, or actuation gates.
- Existing two-human review fixtures remain unchanged and passing.
- Mobile Mission Control explicitly labels the result `Single-operator · development only` and shows production HOLD.
- Full CI, focused policy/security tests, and responsive checks pass before any implementation PR is described as ready.

## Relationship to existing work

Start from accepted `main`; do not mutate frozen PR #78 or `feature/project-aegis`. Review open draft PR #160 and its stacked predecessors as prior art, not as accepted-main functionality. This document does not change their status, signatures, or trust assertions.

Next implementation step: inventory all envelope consumers and authorization transitions, then implement a typed development-only receipt and deny-by-default consumer tests on a separate follow-up branch. Stop before any deployment or hardware gate.
