# AEGIS successor-envelope review — Prior-Art Field Report

Reviewed 2026-09-19. This report narrows the broader AEGIS ecosystem survey to the cryptographic boundary between an exact successor AIRWORTHINESS draft and a later manual acceptance decision.

## Decision

Build the small TruePanel-owned policy adapter and continue using the host's OpenSSH `ssh-keygen -Y verify` implementation. Adapt TUF's transition semantics and in-toto's independent-functionary threshold, but do not import either framework. The resulting packet binds and independently reconstructs the exact draft, requires two distinct current Ed25519 reviewers, expires within 24 hours, and can reach only `ELIGIBLE_FOR_MANUAL_ENVELOPE_ACCEPTANCE`.

No external code, schema, package, service, credential, key, or dataset was incorporated. The implementation adds no runtime dependency. Disposable HoloDeck keys exist only inside a temporary directory during the checkride.

## Strongest candidates

| Candidate | What the code/spec supplies | Maturity and maintenance evidence | Fit, weight, and security | License / attribution | Recommendation and likely saving |
|---|---|---|---|---|---|
| [TUF specification](https://github.com/theupdateframework/specification/blob/7dd5faca4251995063b851c060a12ac915b17ae3/tuf-spec.md) | A root transition must satisfy old and new trust; threshold keys, expiry, and rollback resistance keep update authority separate from content. | Formal, security-focused specification; the repository updated maintainers on 2026-09-17 and clarified threshold semantics on 2026-08-10. | Excellent semantic fit, zero dependency if adapted; adopting a complete repository client would be excessive for one local envelope. | Community Specification License 1.0; sample code Apache-2.0. Implementations do not require specification attribution, but derivative specification text does. | **Adapt semantics.** Avoids inventing the predecessor/successor and threshold model; saves roughly several design-and-review days. |
| [OpenSSH SSHSIG](https://github.com/openssh/openssh-portable/blob/bc41d062cc0f305e49d58430b467c3ce8c822a87/PROTOCOL.sshsig) and [verification regression](https://github.com/openssh/openssh-portable/blob/bc41d062cc0f305e49d58430b467c3ce8c822a87/regress/sshsig.sh) | Purpose namespaces, detached signatures, allowed-signers identity, and mature verification behavior. The actual C path checks the expected namespace. | Widely deployed and actively maintained; upstream commits were present on 2026-09-17 and include a dedicated SSHSIG regression suite. | Best platform fit because TruePanel already wraps the installed binary; no new Python crypto surface, network, or service. | BSD-style collection; no copied code, so no new notice artifact is required. | **Reuse the installed verifier behind TruePanel's adapter.** Saves a cryptographic parser and its security maintenance burden. |
| [in-toto verification](https://github.com/in-toto/in-toto/blob/e352b43ad7cb8915d84c36d791aa61346152a0a3/in_toto/in_toto_verify.py) and [threshold implementation](https://github.com/in-toto/in-toto/blob/e352b43ad7cb8915d84c36d791aa61346152a0a3/in_toto/verifylib.py) | Expiring signed layouts, authorized functionaries, threshold link evidence, and material/product rules. Its tests exercise threshold variation. | Mature CNCF supply-chain project with active dependency and documentation work through 2026-08-27. | Strong conceptual fit, but its general layout and metadata stack is much heavier than this narrow offline boundary. | Apache-2.0; copying code would require notice preservation. No code copied. | **Adapt functionary-threshold and subject-binding ideas.** Defer the package; expected integration cost exceeds current benefit. |
| [Uptane Standard](https://github.com/uptane/uptane-standard/blob/a02f9cace9e842dbc33f2151b47620a50ccc9151/uptane-standard.md) | Separates Director policy from Image artifacts and applies TUF to safety-sensitive field updates. | Established automotive standard; repository licensing was refreshed on 2026-07-24, though substantive repository activity is lighter than TUF/OpenSSH. | Excellent architectural analogy for independent policy and artifact decisions; a full implementation is too heavy and vehicle-specific. | Community Specification License 1.0; implementation attribution is not required, derivative spec text is. | **Architectural inspiration only.** Keeps review, acceptance, and installation as separate authorities. |

## Incorporated shortcut

TruePanel's existing replaceable `OpenSshSignatureVerifier` remains the only cryptographic adapter. The new review layer adds strict TruePanel-owned data shapes and policy checks around it. It independently reconstructs the draft from the accepted envelope, accepted Recovery Coverage Matrix, v2 candidate, appraisal, and exact coverage-review evidence before validating the signed digest. This closes a substitution class that a signature over caller-supplied subject hashes alone would leave open.

The 10-scenario HoloDeck checkride uses OpenSSH itself for signature creation and verification. One exact path becomes eligible for a later manual acceptance decision. One reviewer, expiry, unknown packet fields, draft tampering, automatic acceptance, candidate or predecessor substitution, namespace mismatch, and duplicate reviewer identity all produce `HOLD`.

## Rejected paths

- **Treat a valid review receipt as acceptance.** Rejected because review and acceptance are different authorities. The result contains no accepted or installed state.
- **Trust the packet's draft digest without reconstruction.** Rejected because a caller could substitute mutually consistent packet and draft data.
- **Count two signature objects without distinct identities and keys.** Rejected because one operator could satisfy quorum twice.
- **Embed a signer or production private key.** Rejected because it collapses separation of duty and expands credential exposure.
- **Adopt in-toto or a full TUF/Uptane client.** Rejected for dependency weight, schema surface, and operational complexity disproportionate to the offline local contract.
- **Use Sigstore or a hosted transparency service now.** Deferred: identity privacy, offline availability, trust-root governance, and network dependence remain unresolved.
- **Copy OpenSSH, TUF, Uptane, or in-toto code.** Rejected because the available installed verifier and small local interface provide the benefit without provenance or replacement burden.

## Collaboration opportunity

The strongest collaboration target is the TUF/Uptane maintainer community: ask whether a local appliance's separately reviewed but not yet accepted policy-envelope transition maps cleanly to successive-root expectations, especially when installation authority must remain offline and manual. OpenSSH portable maintainers are the practical secondary contact for SSHSIG/allowed-signers lifecycle guidance. No external contact was made.

## Remaining risk and next gate

The runtime has no operator-owned review signatures, so it correctly remains `HOLD`. HoloDeck proves mechanics with disposable keys, not real reviewer identity or field governance. The next gate is two operator-owned signatures over the exact packet, followed by a separately designed manual acceptance record. That future record must still be unable to install, deploy, or mutate BattleStation.
