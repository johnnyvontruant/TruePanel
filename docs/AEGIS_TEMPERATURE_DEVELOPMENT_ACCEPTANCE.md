# AEGIS development-only temperature acceptance

Reviewed: 2026-10-10

## Decision

The exact 9/9 temperature coverage candidate can now be acknowledged for
**development review only**. This does not change the accepted 8/8 runtime
matrix, install the candidate, deploy code, or authorize production, storage,
network, fan, LCD, bay-LED, or other hardware actions.

The live engine has no JT confirmation and reports
`ACTION_REQUIRED_OPERATOR_CONFIRMATION`. The positive HoloDeck case is an
explicit fixture, labelled `confirmation_authenticated: false`; it proves the
scope boundary but does not fabricate JT identity or a cryptographic signature.

## Architecture and proof

The request binds the complete candidate document, the appraisal's declared
digest, and the complete appraisal document. A confirmation must contain only
the exact JT identity, exact development-only scope, exact acknowledgement,
exact subjects, and a UTC validity window no longer than 24 hours. Unknown
fields, subject substitution, expiry, Vega-as-human, ambiguous wording, and
authority escalation fail closed.

HoloDeck preserves 11 deterministic cases:

- 1 `ACTION_REQUIRED_OPERATOR_CONFIRMATION`;
- 1 fixture `DEVELOPMENT_ACCEPTED_FOR_REVIEW`;
- 9 `HOLD`;
- 0 runtime acceptances, installations, production authorizations, writes, or
  hardware actions.

Mission Control adds a mobile-safe Development Acceptance panel showing the
operator action, authentication truth, and explicit no-authority states.

## Prior-Art Field Report

| Candidate | What was inspected | Recommendation | License / weight |
|---|---|---|---|
| [in-toto Statement v1](https://github.com/in-toto/attestation/blob/main/spec/v1/statement.md) | The spec and protobuf bind an attestation to immutable digest subjects. | Adapt subject binding; keep TruePanel's stricter closed schema. | Apache-2.0 project; no code copied, zero dependency. |
| [SLSA VSA v1.2](https://slsa.dev/spec/v1.2/verification_summary) | A verifier reports policy evaluation over subjects and an evidence bundle. | Adapt the separation between verification result and downstream acceptance. | CC-BY-4.0 spec; no schema or code copied. |
| [TUF specification](https://theupdateframework.github.io/specification/) | Client workflow rejects untrusted metadata/targets and aborts an update cycle safely. | Adapt fail-closed transition semantics; do not import an update system. | CC0/MIT ecosystem; no code copied. |
| [GitHub deployment environments](https://docs.github.com/en/actions/reference/workflows-and-actions/deployments-and-environments) | Required reviewers, optional self-review prevention, wait timers, and deployment-specific gates. | Inspiration only. It targets deployment and cannot honestly create a second human for this team. | Hosted feature; no dependency or copied material. |

### Build versus adopt

Build the small TruePanel-owned evaluator. Its subject/scope boundary is less
than 200 lines, has no secret or network surface, and must compose with existing
AEGIS data. Adopting a deployment platform or full supply-chain framework would
add substantial dependency and operational weight without solving the lone
human team's identity constraint. The in-toto/SLSA communities are the most
promising collaboration opportunity because their subject and verification
models map cleanly to future authenticated receipts.

### Rejected paths and failed assumptions

- A review-ready appraisal is not operator acceptance.
- Vega cannot be represented as a second human or signer.
- Plain explicit acknowledgement is not cryptographic authentication.
- GitHub environment approval is deployment-oriented and would cross the
  current no-deploy boundary.
- A development record cannot be consumed as runtime acceptance or install
  authority.
- Unknown fields are rejected here; in-toto's forward-compatible ignore rule
  is inappropriate for this narrow authority-bearing transition.

## Provenance and safety

Only architectural ideas were adapted. No third-party code, schema, package,
service, executable, credential, private key, signature, or dataset was added.
The work used deterministic fixtures only. BattleStation and every live service,
configuration, storage, network, and hardware control remained untouched.
