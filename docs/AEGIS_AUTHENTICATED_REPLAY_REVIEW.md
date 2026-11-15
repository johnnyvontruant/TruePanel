# AEGIS Authenticated Replay Review

## Increment

This follow-up depends on PR #250 and preserves PR #78 and `feature/project-aegis` unchanged. It adds a separate, two-hour offline SSHSIG statement that binds one exact label-blind replay receipt to exactly one human disposition: `ACCEPT_EVIDENCE` or `HOLD_EVIDENCE`.

Acceptance means only that the preserved evidence may enter manual calibration consideration. It is not field validation, probability calibration, candidate acceptance, installation, promotion, deployment, capture permission, or hardware authority. The receipt registry is owner-protected, append-only by replay digest, and rejects a second disposition rather than overwriting history.

## Recovery Coverage Matrix progress

| Boundary | Detection | Diagnosis/evidence | Guidance | Machine verification | HoloDeck |
|---|---|---|---|---|---|
| Shared cooling degradation | Five fixed signals, label blind | Root cause, 0.95 evidence weight, five observations | Manual review only | Exact canonical replay digest + separate SSHSIG + closed schema | Accept, explicit hold, substitution, escalation, duplicate and policy-drift paths |

The deterministic fixture retains 8/8 trusted recovery coverage, identifies the shared cause at sample 19 versus isolated thresholds at sample 46 (27-sample lead), and records zero labels, field validations, installations, deployments, hardware actions, or runtime writes.

## Prior-Art Field Report (reviewed 2026-11-01)

| Candidate | What it supplies | Fit / maturity / license | Decision |
|---|---|---|---|
| [in-toto Attestation Framework v1.2](https://github.com/in-toto/attestation) | Digest-bound subject, typed predicate, authenticated envelope, verification model | CNCF project; active v1.2 spec and multi-language bindings; Apache-2.0; broader dependency surface than this local gate | Adapt the subject/predicate separation, not the library |
| [SLSA Verification Summary Attestation v1.2](https://slsa.dev/spec/v1.2/verification_summary) | A trusted verifier's explicit pass/fail result over an exact subject and policy | Mature specification; designed for supply-chain levels rather than diagnostic evidence | Adapt signer/verifier/policy binding and explicit result semantics |
| [OPA decision logs](https://www.openpolicyagent.org/docs/management-decision-logs) | Auditable decision ID, input, result, policy revision, masking and replay context | Active CNCF project; Apache-2.0; service/plugin/runtime weight is unnecessary here | Revisit when multiple policies or remote audit aggregation exist |
| [OpenSSH SSHSIG](https://man.openbsd.org/ssh-keygen#Y_sign) | Detached signatures with purpose-specific namespaces and an installed verifier | Mature, already present, no new service or credential custody | Adopt through the existing TruePanel-owned verifier interface |

Actual specifications and implementation-facing documentation were inspected, not repository descriptions alone. The smallest legitimate shortcut is the already-installed SSHSIG primitive: a new workflow namespace prevents a field-checkride confirmation or another signature from being replayed as a review decision. in-toto and SLSA influenced the digest-bound statement shape; no external code was copied.

### Rejected or deferred

- A generic in-toto/DSSE library is deferred: valuable for interoperable exported attestations, but it would add serialization and dependency surface without improving the current local trust root.
- OPA is deferred: policy decision logs are strong prior art, but embedding or operating a policy service for two closed choices is disproportionate.
- Sigstore/Rekor is deferred: a remote transparency service changes availability, privacy, identity, and network assumptions. The local exclusive registry is the safer current boundary.
- A bare UI acknowledgement was rejected because it is mutable, unauthenticated, and not bound to the exact replay receipt.

## Collaboration opportunity

The strongest external conversation is with the in-toto Attestation Framework maintainers about whether a general evidence-review predicate should distinguish evidence acceptance from artifact or deployment acceptance. JT should approach them only after the local predicate and threat model stabilize; no maintainer was contacted during this work.

## Failed paths and open risks

- Confidence remains an evidence weight from a deterministic contract, not a calibrated real-world probability.
- A valid signature proves who signed exact bytes; it does not prove review quality or independence. A second-reviewer threshold remains future work.
- Local exclusive storage prevents overwrite but is not a remote transparency log or trusted timestamp.
- Real field accuracy remains unknown until JT supplies governed evidence and a separately authorized field-validation program exists.

## Deploy status

No deployment, merge, live capture, host access, service change, storage/network mutation, or hardware action is authorized or performed.
