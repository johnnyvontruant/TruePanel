# AEGIS dual-root rotation ceremony

## Outcome

AEGIS now has a deterministic offline governance-root transition contract. One canonical statement binds the exact predecessor and successor roster-manifest digests, consecutive generations, distinct predecessor and successor Ed25519 fingerprints, a two-hour ceremony window, and any compromise-time revocation events. The same bytes must be signed by both roots under a workflow-specific SSHSIG namespace. Success changes reviewer-governance trust only; every field, deployment, runtime, storage, network, and hardware authority remains false.

HoloDeck rehearses seven paths: normal dual signing, a valid compromise-time event, missing predecessor signature, missing successor signature, generation skip, impossible compromise chronology, and authority escalation. Two transitions are trusted and five hold. The fan-degradation reference remains 8/8 covered with five signals, 0.95 evidence confidence, shared cooling at sample 19, isolated thresholds at sample 46, and a 27-sample lead.

## Prior-Art Field Report

| Candidate | Capability and lesson | Platform/dependency fit | License / provenance | Decision |
|---|---|---|---|---|
| The Update Framework | Root N+1 must be signed by thresholds from both root N and N+1; generations advance exactly one; root metadata expires and compromised keys are removed | Exact semantic match; a full repository/client adds unnecessary machinery | Open specification; architectural ideas only | **Adapt.** Dual signatures, exact generation continuity, expiry, and predecessor/successor subject binding. |
| Sigstore root-signing | Distributed hardware keyholders, signing-event review, staging, automated client tests, compromise-time revocation | Excellent ceremony model; its public TUF/CDN/Fulcio/Rekor system is too heavy for local offline review | Apache-2.0 ecosystem; no code copied | **Adapt ceremony and test-before-publish ideas.** JT should approach root-signing maintainers when planning real custody. |
| Uptane | Separates signing roles and recommends urgent root rotation after suspected compromise; warns remote replacement cannot establish endpoint identity after key compromise | Strong safety guidance from adversarial vehicle updates; runtime adoption is irrelevant | Uptane standard; ideas only | **Architectural inspiration.** Preserve manual/offline recovery and role separation. |
| OpenSSH SSHSIG | Local, domain-separated detached signatures with protected allowed-signers inputs | Already installed, audited, minimal weight, replaceable behind TruePanel adapter | OpenBSD/OpenSSH permissive license | **Adopt existing verifier.** Private keys never enter TruePanel. |

Sources inspected on 2026-11-04: [TUF specification](https://github.com/theupdateframework/specification/blob/master/tuf-spec.md), [TUF FAQ](https://theupdateframework.org/docs/faq/), [Sigstore root-signing operations](https://github.com/sigstore/root-signing/blob/main/README.md), [Sigstore threat model](https://docs.sigstore.dev/about/threat-model/), [Uptane deployment guidance](https://uptane.org/docs/latest/deployment/best-practices), and [OpenBSD ssh-keygen manual](https://man.openbsd.org/ssh-keygen).

## Build-versus-adopt and provenance

No third-party code, schema, service, network trust system, credential, key, or production dependency was added. Original TruePanel code adapts published protocol semantics and invokes the already adopted system OpenSSH verifier through a TruePanel-owned interface. Full TUF, Sigstore, Uptane, SPIRE, and online transparency integration were rejected because they expand this offline two-root boundary into a networked control plane.

The most promising collaboration is a design review with Sigstore root-signing or TUF maintainers focused on ceremony custody, threshold sizing, recovery after root-threshold compromise, and publication of intermediate roots. No external contact was made.

## Failed assumptions and risks

- A predecessor digest without a predecessor signature is insufficient continuity.
- A successor signature alone allows an attacker controlling the proposed root to authorize itself.
- Any generation jump hides intermediate trust changes and must hold.
- A revocation timestamp preceding the claimed compromise is internally inconsistent.
- Two fixture keys prove cryptographic dual control, not two independently identified human custodians.
- Compromise-time semantics are preserved but not yet applied to historical reviewer signatures.
- The root ceremony is not independently timestamped or transparency witnessed.

The strongest next step is provisioned human-root custody: define two or more offline keyholders, threshold and recovery rules, verify identities out of band, then rehearse a signed transition whose compromise time is enforced when validating historical reviewer signatures. No live host or hardware work is authorized.
