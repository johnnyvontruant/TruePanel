# AEGIS governed reviewer roster

## Outcome

AEGIS now has a replaceable, root-signed reviewer-identity contract between two-person evidence review and any claim that reviewer quorum is trustworthy. The canonical manifest binds exactly two roles to distinct Ed25519 fingerprints, a generation, a predecessor digest, activation and expiry times, a revocation set, and a threshold of two. Verification uses the existing TruePanel-owned OpenSSH adapter and a workflow-specific SSHSIG namespace. It grants reviewer-quorum eligibility only; all field, installation, deployment, runtime, storage, network, and hardware authority remains false.

HoloDeck rehearses six deterministic paths: active generation, chained rotation, expiration, revocation, duplicate identity, and authority-field escalation. Two valid generations activate; all four unsafe cases hold. The preserved fan-degradation reference remains five corroborating signals, 0.95 confidence, shared-cooling correlation at sample 19 versus isolated thresholds at sample 46: 27 samples earlier.

## Prior-Art Field Report

| Candidate | What it supplies | Maturity / fit | License / dependency | Decision |
|---|---|---|---|---|
| The Update Framework (TUF) | Versioned root metadata, unique-key thresholds, expiration, predecessor-and-successor signing during root rotation | Mature specification and implementations; strongest model for rollback/freeze resistance | Specification/idea only; no runtime dependency or copied code | **Adapt concepts.** Generation, predecessor digest, expiry, unique identities, and fail-closed rotation are implemented behind a TruePanel interface. A full TUF repository is disproportionate for two offline reviewer keys. |
| OpenSSH SSHSIG / allowed signers / KRL | Domain-separated signatures, exact signer identity, validity options, and explicit key revocation | Already installed, audited, low dependency weight, exact platform fit | OpenBSD/OpenSSH permissive license; subprocess boundary already owned by TruePanel | **Adopt existing binary.** Reuse the hardened verifier adapter; keep private keys outside TruePanel. The manifest revocation set is deliberately simpler than KRL for now. |
| in-toto layouts | Owner-signed expiring layout, authorized functionary keys, step thresholds | Mature supply-chain evidence design; good role/functionary analogy | Apache-2.0 ecosystem; adding framework would add substantial dependency weight | **Adapt architecture.** Treat reviewers as functionaries and the root as layout owner; do not add the package. |
| Sigstore trust root | Offline threshold root, TUF-distributed online trust material, rotation and compromise-time revocation | Production public-good infrastructure; valuable operational ceremony model | Mixed permissive ecosystem; network transparency and OIDC are unnecessary here | **Architectural inspiration.** Consider its documented signing ceremony when JT provisions real roots. Do not introduce remote identity or transparency services yet. |
| SPIFFE trust bundles | Named trust domains and bundles that change as keys rotate or are revoked | Strong workload-identity standard, but oriented to online control planes | Apache-2.0; SPIRE would be operationally heavy for offline human review | **Reject runtime adoption.** Borrow explicit trust scope and bundle generation only. |

Sources inspected: [TUF v1.0.37 specification](https://theupdateframework.github.io/specification/v1.0.37/), [TUF security model](https://theupdateframework.github.io/security.html), [OpenBSD ssh-keygen manual](https://man.openbsd.org/ssh-keygen), [in-toto getting started](https://in-toto.io/docs/getting-started/), [Sigstore threat model](https://docs.sigstore.dev/about/threat-model/), and [SPIFFE trust-domain/bundle specification](https://spiffe.io/docs/latest/spiffe-specs/spiffe_trust_domain_and_bundle/). These were reviewed on 2026-11-03.

## Build-versus-adopt and provenance

No third-party source code was copied and no new production dependency was added. The prototype is original TruePanel code informed by published protocols. It invokes the system OpenSSH `ssh-keygen -Y verify` through the pre-existing `OpenSshSignatureVerifier`, so the implementation remains replaceable. OpenSSH's allowed-signers format has richer namespace, validity, certificate-authority, and KRL behavior; TruePanel intentionally retains its narrow exact-principal/Ed25519 profile and enforces lifecycle fields in canonical signed metadata.

The highest-value collaboration opportunity is with TUF maintainers or Sigstore root-signing participants: review the rotation ceremony and decide whether a future real roster should use dual-signed predecessor/successor roots instead of the current single anchored root plus predecessor digest. JT should approach them only after two real reviewer identities and an offline root-custody plan exist.

## Rejected and failed paths

- Full TUF, Sigstore, or SPIRE integration was rejected for this increment: each adds network/control-plane or repository machinery beyond a two-person offline evidence-review boundary.
- OpenSSH certificate authorities and wildcard principals were rejected because they expand the accepted identity surface.
- Automatic key rotation was rejected; rotation remains a signed, reviewed generation transition.
- A mutable “current reviewers” file was rejected because it cannot prove predecessor continuity or preserve exact signed evidence.
- Treating two keys as proof of two people remains an open governance risk; the roster proves distinct cryptographic identities, not human identity assurance.

## Open risks and next step

The governance root is still a deterministic fixture, not provisioned custody. Generation 2 proves predecessor binding but not dual-control root rotation. Revocation has no compromise timestamp, and real reviewer availability, separation of duties, and out-of-band identity verification remain untested. The strongest next step is a documented offline root ceremony and dual-signed root-rotation receipt with compromise-time semantics, followed by a review using two provisioned human keys. No live host, TrueNAS setting, service, storage, network, display, fan, LED, or disk was accessed or changed.
