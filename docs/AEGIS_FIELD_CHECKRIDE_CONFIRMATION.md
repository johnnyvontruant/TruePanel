# AEGIS Offline Field-Checkride Confirmation

## Outcome

This increment adds a separate, short-lived SSHSIG confirmation over one exact passive field-checkride plan. A successful `CONFIRM` makes only a future, operator-supplied sanitized recording eligible for review. It does not provide a recording, capture one, access BattleStation, execute a checkride, validate or install a candidate, deploy software, mutate runtime state, or control hardware.

The statement binds the plan, appraisal receipt, dossier and seven dossier subjects, passive contract, accepted Recovery Coverage Matrix (8/8 trusted, zero gaps), and the established 19-versus-46 sample proof target. It is exported as public material for offline signing; TruePanel accepts neither a private key nor a signer invocation. Evaluation reconstructs the statement from the protected canonical plan, authenticates a distinct SSHSIG namespace, and creates one owner-protected content-addressed receipt. Unknown fields, old namespaces, substitutions, expiry, unsafe registries, symlinks, and replay fail closed.

## HoloDeck evidence

- 12 deterministic paths: two signing-ready statements, one authenticated confirmation, one authenticated operator HOLD, and eight adversarial HOLDs.
- The confirmed path reaches only `ELIGIBLE_FOR_OPERATOR_SUPPLIED_RECORDING_REVIEW`.
- Recordings consumed or captured: 0. BattleStation accesses, field-checkride authorizations, validations, deployments, hardware actions, and runtime writes: 0.
- Shared-cooling proof target remains sample 19 versus isolated-threshold sample 46: 27 samples earlier.
- Preserved evidence: `docs/evidence/aegis-temperature-field-checkride-confirmation-v1.json` (`c423ba4810c40633edb2d0de168fd3126be1af1f1c43459c1d0aace98de6a2bc`).

## Prior-Art Field Report

| Candidate | What the actual specification/code supplied | Fit, maturity, weight, security, licence | Decision |
|---|---|---|---|
| [in-toto Statement v1](https://github.com/in-toto/attestation/blob/50bf01716982189898823e90586075f37cd9bb7d/spec/v1/statement.md) | A fixed statement binds immutable subjects by digest and identifies typed predicate semantics. Its Go implementation rejects a wrong statement type, a missing subject, and a v1 subject without a digest. | CNCF ecosystem; maintained multi-language spec/tests; Apache-2.0; importing the protobuf stack would be disproportionate. | Adapt the digest-bound typed-statement idea behind TruePanel's exact-schema interface; no code copied and no dependency added. |
| [SLSA Verification Summary Attestation v1.2](https://slsa.dev/spec/v1.2/verification_summary) | Separates verifier identity, evaluated artifact, input attestation bundle, policy, and verification result. | Current specification; ecosystem-mature and interoperable; format adoption would bring broader supply-chain semantics than this narrow operator gate needs. | Adapt its verifier/policy/result separation; do not claim SLSA conformance. |
| [TUF roles and metadata](https://theupdateframework.io/docs/metadata/) and [specification](https://github.com/theupdateframework/specification/blob/e2bc7d83d0740aaae8dd7133dd4f237ce3d86b16/tuf-spec.md) | Role-specific keys, expiry, versioning, and signature thresholds compartmentalize trust and resist rollback/replay. | CNCF graduated, strong security analysis and implementations; specification CC0 and implementations vary; a complete update framework is too heavy for a local confirmation receipt. | Adapt role separation, expiry, immutable digests, and fail-closed replay. Consider a two-person threshold only when a second governed reviewer exists. |
| [OpenSSH SSHSIG](https://github.com/openssh/openssh-portable/blob/master/PROTOCOL.sshsig) | Detached signatures include an interpretation namespace explicitly intended to prevent cross-protocol acceptance. OpenSSH's regression suite exercises signature verification failures. | Widely deployed, actively maintained, OS-provided, no service or Python dependency; BSD-style licensing. | Adopt the installed verifier through TruePanel's existing adapter with a new confirmation namespace. No OpenSSH code copied. |
| [Sigstore policy-controller](https://github.com/sigstore/policy-controller) | Admission policies bind signed artifacts to policy and identity. | Active and well-tested Apache-2.0 project, but Kubernetes, registry, Rekor, and certificate assumptions are excessive for an offline NAS review gate. | Architectural inspiration only; rejected as a dependency. |
| [Uptane](https://uptane.org/docs/2.1.0/standard/uptane-standard) | Separates authorization roles and binds metadata for safety-sensitive software distribution. | Mature automotive security standard; a full Director/Image repository and ECU model is an incompatible operational expansion. | Separation-of-duty inspiration only; rejected for integration. |

### Build versus adopt

The useful shortcut is the already-installed OpenSSH verifier. TruePanel retains a small owned schema and policy evaluator because the domain contract is narrower than a supply-chain or vehicle-update framework and must explicitly deny all operational authority. The in-toto, SLSA, TUF, and Uptane ideas are adapted without copying code. This adds no package, daemon, network call, remote trust service, credential, or licence notice obligation beyond documenting provenance.

The most promising collaboration opportunity is with the in-toto/SLSA maintainers: ask whether a narrow human review decision predicate should be standardized, especially how negative authority and explicit HOLD decisions should be represented. OpenSSH remains the practical implementation dependency to monitor.

### Rejected and failed paths

- Reusing the appraisal namespace was rejected because it permits cross-stage signature replay.
- Treating confirmation as a recording, checkride authorization, or validation was rejected; all remain false.
- A mutable “current confirmation” file was rejected in favor of one content-addressed, exclusive receipt per plan.
- Accepting extensible statement fields was rejected; unknown fields fail closed.
- A built-in signing convenience was rejected because it would introduce private-key inputs and signer authority.
- Full in-toto, Sigstore, TUF, or Uptane integration was rejected as dependency and operational weight without corresponding verified value.

## Open risks and next step

This is development evidence, not field validation. The development roster still requires JT governance, and one key is not human separation of duties. The next safe increment is a content-bound recording-review intake that requires this exact receipt, accepts only an operator-supplied sanitized canonical recording, independently verifies privacy/custody/sequence invariants, and still cannot capture from a host or promote a candidate.
