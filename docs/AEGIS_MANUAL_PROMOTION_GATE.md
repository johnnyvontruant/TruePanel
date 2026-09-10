# AEGIS manual promotion gate

This experiment binds independent review to the exact staged tree that an operator may later promote. It produces guidance only; it neither consumes the receipt nor executes promotion.

## Contract

- A content-addressed request binds candidate envelope, validated-stage manifest, staged-tree digest, source and deployed versions, stage/deployment/backup paths, and a one-time nonce.
- The independent-review receipt signs the promotion-request digest.
- The gate requires an unused receipt, pristine validated stage, exact tree and manifest digests, safe sibling rollback path, version agreement, no active incident, healthy services and pools, no safety hold, and verified rollback readiness.
- Passing yields only `READY_FOR_MANUAL_PROMOTION` and the existing `PROMOTE_TRUEPANEL` confirmation requirement.
- Receipt consumption and promotion remain external operator actions. The evaluator performs no writes, restarts, service changes, or deployment.

## HoloDeck results

Nine deterministic paths produce one manual-ready decision and eight holds. Missing review, replayed receipt, stage-tree tamper, dirty stage, active incident, unverified rollback, unsafe backup path, and version mismatch all hold. False-ready paths, promotions, receipt consumption, service changes, runtime writes, production mutation, and control authority remain zero.

## Prior art

TUF and Uptane show why metadata, target content, version movement, and rollback resistance must be evaluated together. GitHub deployment environments demonstrate a useful separation between automated readiness checks and a distinct protected deployment approval. TruePanel adapts those semantics without adding a hosted deployment system or external code.

Rejected paths include signing only the successor envelope, allowing approval to trigger promotion, keeping the nonce ledger inside this read-only evaluator, permitting an active incident during upgrade, and accepting a rollback path outside the deployment parent.

The strongest next step is an operator-owned verifier adapter and a dry-run integration that produces this request directly from TruePanel's real validated-stage manifest and deterministic tree digest.
