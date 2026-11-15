# AEGIS Two-Person Replay Review

## Increment

This follow-up depends on PR #254 and preserves PR #78 and `feature/project-aegis` unchanged. It independently reconstructs the primary replay-review statement, signature, receipt, and replay identity before permitting a second, distinct public-key identity to record `CONCUR_ACCEPT_EVIDENCE` or `DISSENT_HOLD_EVIDENCE`.

Concurrence reaches only two-person evidence-review quorum for manual calibration consideration. It does not establish field accuracy, accept or install a candidate, authorize capture, promote a policy, deploy software, mutate runtime state, or control hardware.

## Recovery Coverage Matrix progress

| Fault boundary | Detection | Evidence-backed diagnosis | Guidance | Machine verification | HoloDeck regression |
|---|---|---|---|---|---|
| Shared cooling degradation | Five fixed signals | 0.95 evidence weight; sample 19 shared cause | Independent review before calibration consideration | Reconstruct primary SSHSIG and receipt; require distinct second key and exact concurrence | Concur, dissent, authority escalation, exclusive receipt, duplicate replay |

The fixture retains 8/8 trusted coverage, five supporting signals, and the 27-sample lead over isolated thresholds. Labels, field validations, installations, deployments, hardware actions, and runtime writes remain zero.

## Prior-Art Field Report (reviewed 2026-11-02)

| Candidate | What it supplies | Maturity, fit, and license | Recommendation |
|---|---|---|---|
| [TUF specification v1.0.36](https://theupdateframework.github.io/specification/v1.0.36/) | Unique-key threshold counting, scoped roles, expiry, rollback resistance | Mature CNCF specification; implementations commonly Apache-2.0/MIT; full update framework is out of scope | Adopt unique-key quorum semantics, not the framework |
| [in-toto layouts](https://in-toto.io/docs/getting-started/) | Authorized functionaries, step thresholds, signed material/product evidence | Mature CNCF project, Apache-2.0; supply-chain command model is broader than evidence review | Adapt distinct functionary identity and chained evidence semantics |
| [Sigstore policy-controller](https://docs.sigstore.dev/policy-controller/overview/) | Multiple signature/attestation authorities and policy composition | Active, Apache-2.0, Kubernetes/OCI focused and explicitly still developing | Defer runtime adoption; reuse the explicit multi-authority idea |
| [OPA decision logs](https://www.openpolicyagent.org/docs/management-decision-logs) | Traceable decision ID, policy revision, input/result, masking | Mature CNCF project, Apache-2.0; adds service/plugin weight | Revisit when review policies require centralized audit |
| OpenSSH SSHSIG | Purpose-scoped detached signature with installed local tooling | Mature and already wrapped by TruePanel; no new service or dependency | Adopt through the existing TruePanel-owned interface |

Actual specifications and implementation-facing documentation were inspected. No third-party code, schema, service, credential, key, dataset, Rego/CUE policy, or package was copied. TUF's rule that one key ID counts once is the key shortcut: TruePanel explicitly rejects identical primary and reviewer fingerprints rather than counting two signatures from one identity.

## Rejected candidates and failed approaches

- Reusing the primary reviewer key was rejected: two signatures from one identity are not two-person review.
- Trusting the primary receipt digest alone was rejected: the original statement, signature, exact replay, and receipt are reconstructed.
- Sigstore policy-controller was not embedded because Kubernetes, OCI, Fulcio, Rekor, and policy-runtime assumptions are disproportionate here.
- A mutable quorum flag was rejected in favor of one exclusive receipt keyed by the primary review digest.
- Concurrence does not elevate the primary evidence score into calibrated probability or field validation.

## Collaboration opportunity and risks

TUF and in-toto maintainers are the strongest prospective collaborators on portable unique-functionary threshold semantics for evidence review. No maintainer was contacted.

Open risks remain: fixture keys are not governed human identities; two local signatures are not independently witnessed transparency; both implementations still run in the same package; and synthetic evidence does not prove real field accuracy.

## Deploy status

No merge, deployment, BattleStation access, live capture, service/configuration change, storage/network mutation, credential handling, or hardware action was performed.
