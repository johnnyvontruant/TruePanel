# AEGIS single-operator development receipt

Status: development-only, hardware-isolated, not accepted or deployed.

## Result

TruePanel now represents the actual team honestly: JT is the sole accountable
human approver; Vega's review and the deterministic test report are evidence,
not a second signature. A valid receipt reaches only
`ELIGIBLE_FOR_DEVELOPMENT_CANDIDATE_REVIEW`.

The type, OpenSSH namespace, decision, and consumer are distinct from the
existing two-human production-review path. One human using two keys still
fails its distinct-reviewer quorum.

## Consumer inventory

| Consumer | Existing authority input | Development receipt result |
|---|---|---|
| Single-operator development review | Exact development result schema and status | Allowed only for development candidate review |
| Independent acceptance (`aegis.acceptance`) | Two distinct reviewer identities and keys | Rejected: different schema, namespace, decision, and quorum |
| Manual promotion (`aegis.promotion_gate`) | Exact production acceptance schema plus `ELIGIBLE_FOR_OPERATOR_PROMOTION` | Rejected: both schema and status are pinned |
| Final handoff (`aegis.final_handoff`) | A ready manual-promotion gate | Rejected transitively because no ready gate can be produced |
| Guarded upgrade (`upgrade.promotion`) | Explicit `PROMOTE_TRUEPANEL` confirmation and lifecycle inputs | No receipt parameter or adapter exists |
| Hardware commands (`hardware.commands`) | Command-specific configuration/interlocks | No receipt parameter or adapter exists |
| Lifeline identify/replacement | Session, identity, authorization and hardware adapter gates | No receipt parameter or adapter exists |

The shared `authority_boundary` is deny-by-default: the only allowed
capability is `development_candidate_review`; production acceptance,
deployment, hardware actuation, storage writes, and network reconfiguration
are explicitly denied.

## HoloDeck proof

Fifteen deterministic scenarios produced one development-eligible decision,
nine HOLD decisions, and five explicit consumer denials. The negative paths
cover missing and expired signatures, packet extension, candidate tampering,
production-namespace substitution, authority escalation, replay, one human
using two keys, and the real manual-promotion consumer.

Measurements: zero false eligibility, production acceptances, deployments,
hardware actions, storage writes, network changes, automatic promotions, or
runtime writes. Recovery Coverage Matrix remains 8/8 trusted with zero gaps.

Preserved evidence: `docs/evidence/aegis-single-operator-development-v1.json`.

## Prior-Art Field Report

Research was refreshed against actual upstream specifications and code on
2026-09-20.

| Candidate | What it supplies | Maturity / maintenance / tests | Platform and dependency fit | License / attribution | Decision and saved effort |
|---|---|---|---|---|---|
| [TUF specification](https://github.com/theupdateframework/specification/blob/master/tuf-spec.md) | Named roles, scoped delegation, explicit signature thresholds, expiry and rollback resistance | CNCF specification with versioned releases and broad conformance ecosystem | Excellent semantic fit; a full client would be excessive here | CC-BY 4.0 specification; concepts attributed | Adapt separate-role and threshold semantics; avoids inventing an ambiguous global “approval” |
| [in-toto layout implementation](https://github.com/in-toto/in-toto/blob/develop/in_toto/models/layout.py) | Step-specific authorized keys, threshold, expected commands and inspections | Active reference implementation with validation and tests | Strong model; Python runtime dependency is unnecessary for one local receipt | Apache-2.0 | Adapt subject/functionary separation; do not import code |
| [SLSA VSA](https://github.com/slsa-framework/slsa/blob/main/spec/verification_summary.md) | Exact subject, verifier identity/version, policy digest, input attestations and pass/fail result | Versioned specification maintained by the SLSA community | Excellent for binding automated review as evidence without calling it human approval | Community specification; concepts attributed | Adapt subject/policy/evidence separation; prevents Vega evidence from becoming authority |
| [Sigstore Cosign](https://github.com/sigstore/cosign/blob/main/README.md) | Keyless, hardware/KMS and public-key verification; identity constraints; offline bundles | Active, audited ecosystem with E2E tests and stable 2.x maintenance | Technically strong but adds Go binary, identity/privacy and trust-root operations | Apache-2.0 | Defer adoption; existing OpenSSH SSHSIG adapter saves the integration and operational burden |
| [GitHub deployment environments](https://docs.github.com/actions/deployment/targeting-different-environments/using-environments-for-deployment) | Environment-scoped approvals, branch restrictions and secrets boundary | Hosted mature platform behavior | Useful analogy, but would couple local NAS governance to a hosted control plane | Documentation terms; no code copied | Adapt environment scoping only |

### Build versus adopt

Build the small typed policy evaluator around TruePanel's existing verifier.
The implementation is standard-library only, under 300 lines, replaceable,
and directly testable against TruePanel's consumers. Adopting TUF, in-toto or
Cosign now would add substantially more code, trust-root operation, and
identity/privacy choices than this development-only decision requires.

No external code, schema, package, service, credential, key, or dataset was
incorporated. Only the named architectural semantics were adapted.

### Rejected paths and failed assumptions

- Reusing the production receipt with threshold one was rejected because it
  silently changes the meaning of an existing type.
- Counting Vega as a human reviewer was rejected because evidence is not
  accountable signing authority.
- One human with two keys was proven insufficient for the two-human policy.
- A generic `approved: true` flag was rejected because untyped consumers can
  accidentally coerce weak authority into strong authority.
- Cosign keyless signing was deferred because a public transparency service
  can expose identity and adds online trust-root lifecycle work.
- GitHub environment approval was not adopted as a production dependency;
  TruePanel must remain verifiable offline and locally replaceable.

The strongest collaboration opportunity is the SLSA/in-toto maintainer
community: TruePanel's compact verifier/evidence split is directly aligned
with VSA subject-policy binding, while its explicit “AI evidence is not human
authority” case could become a useful small-system profile.

## Boundaries and next step

The operator signature in HoloDeck is simulated; no production key or
signature was created. The runtime therefore shows
`AWAITING_OPERATOR_SIGNATURE`. The next step is to define JT's protected
development public-key roster and reproduce the exact packet with a real
operator-owned detached signature. That remains a development review only;
production acceptance and deployment require separate decisions.
