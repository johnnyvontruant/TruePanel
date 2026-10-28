# AEGIS independent score review

Reviewed 2026-10-25. This increment independently reconstructs an immutable
authenticated calibration score. It does not create a second score, reinterpret a
failed result, validate a candidate, or grant operational authority.

## Architecture and trust boundary

The reviewer accepts only the exact predeclared statistical contract, frozen
440-case manifest, canonical operator-signed label statement, detached SSHSIG, and
committed score receipt. It independently:

1. verifies the protected public-key roster and original label signature;
2. checks every signed outcome against the complete frozen membership;
3. reconstructs the confusion matrix without calling the producer's score helper;
4. independently implements the Wilson bounds and nearest-rank p10 rule;
5. compares every metric, gate, digest, subject, and negative-authority claim;
6. writes one public review receipt without touching the score registry.

Both passing and failing receipts can reach
`CALIBRATION_SCORE_INDEPENDENTLY_RECONSTRUCTED`. That state says the committed
calculation was reproduced. It is not field validation, acceptance, installation,
promotion, deployment, or hardware authority.

## Prior-Art Field Report

| Candidate | What it supplies | Maturity / maintenance | Fit and dependency weight | License / obligations | Recommendation |
| --- | --- | --- | --- | --- | --- |
| [in-toto Test Result](https://github.com/in-toto/attestation/blob/main/spec/predicates/test-result.md) | Subject, configuration, overall result, and named pass/warn/fail outcomes | Versioned predicate in an actively maintained specification with generated bindings and tests | Excellent vocabulary, but its generic pass/fail shape cannot represent this review's Wilson bounds, denominators, or lead distribution without an extension | in-toto software is Apache-2.0; project documentation/specification has separate documented licensing and attribution expectations | Adapt subject/configuration/result separation; do not import a runtime |
| [in-toto eval-result proposal](https://github.com/in-toto/attestation/issues/565) and [proofbundle](https://github.com/b7n0de/proofbundle) | Metric/comparator/threshold evidence, pre-registration binding, optional per-sample commitments, and offline signatures | Promising and unusually close to AEGIS, but the predicate is still an open proposal; proofbundle is independently maintained | Potential future interchange shortcut. Its Merkle, selective-disclosure, timestamp, and cryptography machinery is unnecessary for the present local review | Proposal text is not a released standard; proofbundle reports MIT licensing and would require notice preservation if code were adopted | Track and collaborate; do not depend on an unsettled predicate or copy code now |
| [SLSA verification summaries](https://slsa.dev/spec/v1.2/verifying-artifacts) | Digest-bound prior-verification result, verifier identity, policy, and evidence references | Approved, actively maintained specification | Strong model for a compact review receipt. Full supply-chain levels and dependency traversal are outside this calibration gate | Newer specification content uses Community Specification License 1.0; attribution applies | Adapt verifier/policy/evidence separation only |
| [TUF consistent snapshots](https://theupdateframework.github.io/specification/latest/) | Non-ambiguous content identity and safe coexistence of immutable snapshots | Mature, security-reviewed specification with multiple production implementations | Its hash/version naming reinforces non-replacement, but update transport and role delegation are unnecessary | Community Specification License 1.0; specification attribution applies | Adapt immutable digest reference; do not add TUF runtime code |
| [in-toto attestation-verifier](https://github.com/in-toto/attestation-verifier) | Policy-driven material/product and attribute verification across attestations | Real tests and active history, but its own README labels it a prototype that must not be used in production | Useful code-reading reference; Go runtime, layout machinery, and prototype status outweigh saved work | Apache-2.0 if later adopted, with notice obligations | Reject integration; retain the fail-closed inspection idea |
| [Reproducible Builds verifier ecosystem](https://reproducible-builds.org/tools/) | Independent rebuild, input reconstruction, and artifact comparison | Mature cross-distribution practice with several maintained tools | The central idea—reproduce from fixed inputs, then compare—is an excellent match. Package-building backends are not | Tool-specific licenses; no source incorporated | Adapt the reconstruction discipline |

## Adopted and rejected work

TruePanel adapted only architectural semantics: digest-bound subjects, explicit
configuration, verifier identity, independent reconstruction, immutable references,
and the strict separation of metric evidence from decisions. The installed OpenSSH
verifier remains behind a TruePanel-owned interface.

No third-party source, schema, library, package, service, credential, key, dataset,
or generated binding was copied. There are therefore no new runtime dependencies or
third-party notices in this increment.

Rejected paths:

- trusting the producer's receipt digest without recomputing its metrics;
- calling the original private scoring helper and calling that independent;
- reviewing only passing results while leaving failures rerunnable;
- treating a generic test-result `PASSED` field as the statistical record;
- adopting the emerging eval-result predicate before it is accepted and versioned;
- adding in-toto's prototype verifier after its own production-use warning;
- adding a transparency service, timestamp authority, Merkle tree, or distributed
  ledger before the local one-shot threat model needs one;
- allowing a review receipt to write the score registry or authorize a candidate.

## HoloDeck evidence

`TP-EXP-0040` preserves 12 deterministic paths: one passing and one failing score
reconstruct exactly, while ten mutated, substituted, noncanonical, missing, or unsafe
paths hold. The passing fixture retains the 40-positive / 400-negative cohort,
0.912378 sensitivity lower bound, 0.009512 false-positive upper bound, 0.008655
abstention upper bound, and 27-sample median/p10 lead. Score-registry writes,
re-evaluations, label changes, threshold changes, validations, acceptances,
installations, deployments, hardware actions, and production writes remain zero.

Evidence: `docs/evidence/aegis-temperature-independent-score-review-v1.json`.

## Collaboration opportunity and open risks

The strongest collaboration opportunity is the in-toto attestation maintainers and
the eval-result proposal authors: AEGIS is a concrete NAS reliability example of a
predeclared, signed, offline-recomputed metric record that must remain separate from
any decision or action receipt.

Open risks:

- the alternate implementation is independent at the function level but remains in
  the same Python package and process;
- no real JT signature, field cohort, label set, or committed score exists;
- the local POSIX custody checks are not a distributed transparency log;
- reconstructed fixture accuracy is not field validation;
- an operator decision about whether to accept a reviewed score is intentionally
  still absent.

The next defensible gate is a separately scoped, operator-authenticated calibration
decision receipt that references this review by digest and can record accept or hold,
but still cannot install, deploy, or actuate hardware.
