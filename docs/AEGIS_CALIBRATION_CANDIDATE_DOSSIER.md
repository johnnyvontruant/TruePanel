# AEGIS Calibration Candidate Dossier

## Outcome

This increment assembles one immutable, read-only candidate dossier only after independently reverifying the exact operator decision SSHSIG and receipt, independent review, sealed score, detector subject, accepted Recovery Coverage Matrix, and preserved HoloDeck evidence. Success means only `READY_FOR_MANUAL_CALIBRATION_CANDIDATE_REVIEW`.

The dossier cannot validate, accept, install, deploy, promote, or actuate anything. It never reads a private key, never contacts BattleStation, and never changes a runtime or score registry.

## Architecture and evidence

The assembler verifies every digest edge before writing one owner-protected, content-addressed JSON document. The operator decision remains valid only while its exact signed statement, signature, review, and public roster reconstruct. The score receipt must bind the same detector contract as the review. Recovery coverage must be 8/8 trusted with zero contract errors. HoloDeck proof must preserve the 27-sample shared-cooling lead, one passing ACCEPT, zero failing ACCEPTs, and zero unsafe readiness or operational actions.

TP-EXP-0042 rehearses eight paths: one complete dossier becomes ready for manual review; coverage drift, detector substitution, unsafe HoloDeck evidence, authority escalation, occupied output, missing score, and noncanonical score all HOLD.

## Prior-Art Field Report

| Candidate | What it supplies | Maturity / maintenance | Fit and dependency weight | License / attribution | Recommendation |
|---|---|---|---|---|---|
| in-toto Attestation Bundles | A bundle is a collection of authenticated attestations; each entry still needs independent authentication and parsing. | CNCF project with a versioned specification and conformance-oriented ecosystem. | Excellent architectural fit; importing its full envelope stack would be unnecessary for this local JSON/SSHSIG boundary. | Specifications are openly published; no code or schema copied. | Adapt the bundle semantics, keep TruePanel-owned schema and verifier. |
| Sigstore protobuf Bundle | A portable object binds verification material, content, signature, and optional transparency/timestamp evidence. | Active production ecosystem with strong interoperability and test investment. | Valuable future shortcut if public transparency becomes necessary; current dependency and service footprint are too large for an offline NAS development gate. | Apache-2.0 project; adoption would require notices. No package or code incorporated. | Revisit for external transparency, do not adopt now. |
| IETF SCITT / RFC 9943 | Separates a signed statement from a registration receipt and treats transparency as evidence of registration, not truth. | Standards-track work with an issued architecture RFC and active protocol drafts. | Strong semantic fit for a later auditable receipt; a transparency service is outside this increment and offline trust model. | IETF document terms; concepts only. | Adapt the statement/receipt distinction. |
| SLSA provenance | Explicit subjects and authenticated provenance make artifact identity reviewable. | Widely used supply-chain specification. | Its subject-digest discipline maps directly; the full build-provenance predicate does not describe calibration evidence. | Specification concepts only; no schema copied. | Adapt content-addressed subject discipline. |
| OpenSSH SSHSIG | Offline namespace-separated signature verification using an installed, audited executable. | Mature and already exercised by TruePanel's negative tests. | Best platform fit and zero new Python dependency. | OpenBSD/ISC-style OpenSSH licensing; executable invoked behind a TruePanel interface. | Continue using the installed verifier. |

### Build versus adopt

TruePanel keeps a small owned dossier schema because its policy fields—Recovery Coverage Matrix state, HoloDeck measurements, and explicit negative hardware authority—are domain-specific. The design adapts in-toto bundle composition, Sigstore verification-material binding, SCITT's statement-versus-receipt distinction, and SLSA subject digests. No third-party code, schema, package, service, credential, key, or dataset was copied or added.

Rejected for this increment: a Sigstore transparency-log integration because it adds network/service trust and operational weight; a generic in-toto layout because it does not encode AEGIS's safety floors; and treating a SCITT receipt as appraisal because the standards explicitly separate registration evidence from trust decisions.

The strongest collaboration opportunity is with the in-toto/Sigstore maintainers on portable multi-attestation bundle verification and with the SCITT community on offline-to-transparent receipt promotion. JT should approach those projects only if TruePanel later needs cross-host exchange or public accountability.

## Failed approaches and risks

- Accepting pretty-printed preserved HoloDeck evidence only through a canonical-JSON parser rejected the repository's existing human-reviewable evidence. The final path hashes the exact protected bytes while strictly validating their parsed policy fields.
- Merely checking a decision receipt digest did not prove that its detached SSHSIG remained valid; the dossier now reconstructs and verifies the original statement and signature.
- A valid score digest was insufficient because it could refer to a different detector; the score, review, and decision must all name the same detector contract.

Open risks are deliberate: the fixture identities are not JT's key, evidence remains development-only, no real field recordings are represented, and manual appraisal is still required before any separately designed field-checkride gate.
