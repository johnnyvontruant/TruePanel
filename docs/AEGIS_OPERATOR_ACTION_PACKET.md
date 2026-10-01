# AEGIS content-bound operator action packet

## Outcome

The read-only field ceremony now produces a deterministic, human-readable
packet for exactly one missing JT-owned input. The packet binds the complete
ceremony result, completed-stage list, reviewed verifier, release receipt,
required public input, and ordered operator instructions. It cannot satisfy
the action it describes, claim independent delivery, request a private key, or
widen development-only authority.

This closes the presentation gap between a machine-readable `next_action` and
the instructions JT actually reviews. Any instruction, digest, ceremony,
verifier, scope, or authority change reconstructs differently and produces
`HOLD`.

## Packet contract

| Field | Bound meaning | Safety boundary |
| --- | --- | --- |
| Ceremony digest | Exact semantic field-ceremony result | An eligible or held result cannot become an action packet |
| Completed-stage digest | Exact evidence already accepted by the coordinator | Earlier gates cannot be hidden or reordered |
| Verifier identities | Source digest plus raw release-receipt digest | The packet is not the independently obtained verifier |
| Required public input | One of the five JT-owned ceremony inputs | Private material is never requested |
| Ordered steps | Exact operator-visible procedure for this gate | Presentation drift fails reconstruction |
| Authority map | Development-only, all stronger authorities false | Verification cannot satisfy the action or promote anything |

Mission Control names the packet as a public explanation only. Its phone-safe
development panel continues to distinguish missing operator material as
`ACTION REQUIRED` and supplied invalid evidence as `HOLD`.

## HoloDeck evidence

The deterministic checkride covers ten scenarios: one exact packet verifies,
seven substitutions hold, and two non-action ceremony states are denied.
Attacks cover action, verifier, authority, private-key, independence,
unexpected-field, and ceremony substitution. There are zero action
satisfactions, manufactured independent channels, private-key inputs, signer
invocations, production acceptances, deployments, hardware actions, or runtime
writes. The accepted Recovery Coverage Matrix remains 8/8 trusted with zero
gaps.

Preserved evidence:
[`docs/evidence/aegis-operator-action-packet-v1.json`](evidence/aegis-operator-action-packet-v1.json)
(`5115dc83c594e038a7c171a8dc67c076b36b97e7370ffbd4d30f775229de6475`).

## Prior-Art Field Report

| Candidate | What the code and documentation supply | Maturity, fit, and security | License / attribution | Recommendation |
| --- | --- | --- | --- | --- |
| [Sigstore root-signing](https://github.com/sigstore/root-signing) | Signing-event pull requests, keyholder instructions, separately held keys, and review before signature submission | Operationally mature public-root ceremony; its multi-keyholder production workflow is deliberately stronger and heavier than TruePanel's single-operator development scope | Apache-2.0 repository; no source copied | Adapt the staged action-card and external-key ceremony ideas |
| [in-toto record](https://github.com/in-toto/in-toto/blob/develop/in_toto/in_toto_record.py) | Actual two-step start/stop recording binds materials and products to ordered work | Mature, tested supply-chain implementation, but its recorder loads signing keys and adds a runtime/schema unnecessary here | Apache-2.0; no source or schema copied | Adapt ordered evidence semantics; reject the recorder in this boundary |
| [TUF](https://theupdateframework.github.io/specification/latest/) | Explicit roles, threshold policy, expiry, and fail-closed metadata transitions | Mature security architecture; full repository metadata and role rotation are disproportionate for one explanatory packet | Specification and implementations have project-specific licenses; no code incorporated | Adapt role and transition separation only |
| [RSTUF ceremony guidance](https://repository-service-tuf.readthedocs.io/en/latest/guide/deployment/setup.html) | Offline root-key custody and ceremony-oriented setup | Useful operational model, but deploying a repository service would add network, credential, and lifecycle weight without improving this read-only step | Project documentation/code attribution would apply if incorporated; none was | Use as ceremony inspiration, not a dependency |
| [OpenSSH SSHSIG](https://github.com/openssh/openssh-portable/blob/master/PROTOCOL.sshsig) | Namespaced detached signatures and a deployed verifier | Already used behind a TruePanel-owned adapter; narrow interface and no new dependency | BSD-style OpenSSH license; executable invoked, source not copied | Keep for the later signature gate, not for action-packet trust |

The strongest collaboration opportunity is the Sigstore root-signing and
TUF-on-CI maintainer community. Their practical experience turning exact
metadata changes into reviewable signing events could improve TruePanel's
operator ceremony without pretending the lone-human development policy is a
multi-person production quorum.

Only architectural semantics were adapted. No external source, package,
schema, service, credential, key, or dataset was added. The strongest
candidates were inspected at their implementation and operator-documentation
boundaries rather than selected from project descriptions alone.

Rejected paths:

- letting a verified packet count as the missing independent confirmation;
- including a signer or accepting a private-key path for convenience;
- signing the explanatory card instead of the canonical signing session;
- auto-executing the action after packet verification;
- treating same-channel delivery as independent evidence; and
- adding in-toto, TUF, Sigstore, or RSTUF runtime infrastructure for a small
  replaceable interface.

The invalidated assumption was that a machine-readable `next_action` alone
fully bound the human handoff. It named the gate but did not authenticate the
instructions, completed-stage summary, or verifier identity presented to JT.

## Safety and next gate

This increment is simulation and public read-only verification only. It
creates no JT key, roster, signature, production acceptance, deployment,
service change, hardware action, or runtime write. The real next gate remains
JT independently confirming the reviewed verifier fingerprint; the verified
packet merely makes that action precise and auditable.
