# AEGIS read-only field ceremony

## Outcome

The field ceremony composes the existing verifier bootstrap, public roster,
public-only signing kit, dual audit, detached SSHSIG, and audit-bound return
verification into one read-only state machine. It deliberately does not create
any operator-owned artifact. An omitted artifact identifies the next action;
a supplied artifact that fails validation produces `HOLD`.

The only successful terminal state is
`ELIGIBLE_FOR_DEVELOPMENT_CANDIDATE_REVIEW`. Production acceptance,
deployment, hardware control, storage writes, and automatic promotion remain
false.

## Ceremony contract

| Stage | JT-owned input | Successful evidence | Missing | Invalid |
| --- | --- | --- | --- | --- |
| Verifier identity | Independently obtained SHA-256 confirmation | Content-pinned standalone verifier | `ACTION_REQUIRED_INDEPENDENT_VERIFIER_CONFIRMATION` | `HOLD` |
| Operator identity | Protected public-only Ed25519 roster | Exact `jt-development-review` fingerprint | `ACTION_REQUIRED_PUBLIC_ROSTER` | `HOLD` |
| Review payload | Exported public signing kit | Canonical session, review card, and manifest | `ACTION_REQUIRED_SIGNING_KIT_EXPORT` | `HOLD` |
| Diverse audit | Standalone audit witness | Two digest-identical audits | `ACTION_REQUIRED_INDEPENDENT_KIT_AUDIT` | `HOLD` |
| Authorization | Detached offline SSHSIG | Audit-bound returned-signature verification | `ACTION_REQUIRED_OFFLINE_SIGNATURE` | `HOLD` |

The independent-channel stage requires a content-bound, 30-minute operator
attestation receipt. A same-repository value is rejected as a comparison
method, and the receipt is explicitly not misrepresented as cryptographic
proof of JT or the independent channel.

## HoloDeck evidence

The deterministic checkride covers 13 scenarios: five operator action gates,
one exact development-eligible path, and seven adversarial holds. Adversarial
cases cover fingerprint substitution, wrong roster, stale witness, invalid
signature, kit drift, material substitution, and checkout drift. The accepted
Recovery Coverage Matrix remains 8/8 trusted with zero gaps.

Preserved evidence:
[`docs/evidence/aegis-field-ceremony-v1.json`](evidence/aegis-field-ceremony-v1.json)
(`f4e688726fe657e5c0c7b61fbb9c2af02e94e30cf09e1ff84e4574e044fc968f`).

## Prior-Art Field Report

| Candidate | Capability and maturity | Fit / dependency / security | License and attribution | Recommendation |
| --- | --- | --- | --- | --- |
| [in-toto](https://github.com/in-toto/in-toto) | Ordered supply-chain layouts and signed link metadata; mature ecosystem with extensive tests | Strong model for ordered evidence, but its Python verifier would add a runtime and schema larger than this ceremony needs | Apache-2.0; attribution required if code is used | Adapt the ordered-stage and subject-binding ideas; do not add its runtime here |
| [SLSA verification summary attestations](https://slsa.dev/spec/v1.2/verification_summary) | Separates subject, policy, verification result, and verifier identity | Excellent vocabulary for the final result; no dependency is needed to use the architecture | Community specification; no code incorporated | Adapt the result semantics |
| [TUF](https://theupdateframework.github.io/specification/latest/) | Mature client-side trust transitions, explicit roles, thresholds, and rollback protection | Strong fail-closed transition model; full metadata rotation is disproportionate for one development-only operator | Specification and implementations have project-specific licenses; no code incorporated | Adapt explicit transition gates, not the implementation |
| [Reproducible Builds](https://reproducible-builds.org/docs/independent-verification/) | Independent reproduction and comparison rather than trusting a producer's declaration | Directly supports the diverse-audit boundary and has zero runtime weight | Documentation/technique only | Keep the independent witness design |
| [OpenSSH SSHSIG](https://github.com/openssh/openssh-portable/blob/master/PROTOCOL.sshsig) | Deployed detached signatures with namespaces and an audited regression suite | Already installed, narrow interface, no new Python dependency, private key remains outside TruePanel | BSD-style OpenSSH license; executable is invoked, no source copied | Adopt through the existing TruePanel-owned adapter |

Capability and maintenance judgments above are based on the projects' public
specifications, repositories, and test material reviewed for this increment.
Only architectural semantics and the installed OpenSSH/Git executables are
used. No external source code, package, schema, service, credential, key, or
dataset was copied into TruePanel.

The strongest collaboration opportunity is the in-toto/SLSA maintainer
community: its subject/policy/result conventions could help keep TruePanel's
small ceremony interoperable without importing a heavyweight runtime.

Rejected approaches:

- auto-creating JT's roster, kit, witness, or signature inside the coordinator;
- treating missing operator material as evidence corruption rather than naming
  the next operator action;
- accepting invalid supplied evidence as merely incomplete;
- claiming a same-channel digest is cryptographic proof of independent delivery;
- skipping directly to signature verification without revalidating every prior
  stage; and
- adopting a general attestation/orchestration framework before the small
  replaceable interface proves insufficient.

The invalidated assumption was that a collection of individually safe commands
automatically forms a safe operator workflow. Without a coordinator, missing
artifacts and invalid artifacts were operationally ambiguous, and a later stage
could be attempted without a clear view of the earlier gates.

## Safety and next gate

This increment is simulation and read-only verification only. It creates no JT
key, real roster, real signature, production acceptance, deployment, service
change, hardware action, or runtime write. The next gate is JT independently
confirming the reviewed verifier fingerprint and provisioning the protected
development public roster; the coordinator will then name the following gate.
