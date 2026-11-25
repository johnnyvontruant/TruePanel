# AEGIS Authenticated Calibration Candidate Appraisal

## Outcome

This increment creates an explicit human-appraisal boundary over the exact content-bound candidate dossier. An operator may sign `APPROVE_FOR_MANUAL_FIELD_CHECKRIDE_PLANNING` or `HOLD_CALIBRATION_CANDIDATE_APPRAISAL`. Approval permits planning only: it cannot start or authorize a field checkride, validate or accept a candidate, install software, deploy, promote automatically, write runtime state, or actuate hardware.

The appraisal independently recomputes the dossier digest, requires all seven exact subject digests, the accepted 8/8 Recovery Coverage Matrix, the preserved 27-sample HoloDeck lead, and every negative authority claim. The signed statement binds decision, rationale, two-hour validity window, public-key fingerprint, dossier identity, coverage, proof, and scope under a new SSHSIG namespace. The receipt is owner-protected, content-addressed, and non-replaceable.

## HoloDeck proof

TP-EXP-0043 rehearses twelve paths: two statements are ready for offline signature, one authenticated APPROVE reaches manual field-checkride planning, one authenticated HOLD remains terminal, and eight adversarial paths HOLD. Wrong namespace, dossier substitution, unknown fields, authority escalation, unsafe registry permissions, duplicate replay, expiry, and symlink substitution all fail closed.

Field-checkride authorizations, validations, candidate acceptances, installations, deployments, hardware actions, automatic promotions, and unsafe-ready results remain zero.

## Prior-Art Field Report

| Candidate | Capability and lesson | Maturity / activity | Platform fit and dependency weight | License / attribution | Recommendation |
|---|---|---|---|---|---|
| in-toto Attestation Framework | Typed predicates bind authenticated metadata to exact subjects; monotonic parsing prevents ignored evidence from turning DENY into ALLOW. | CNCF project with a versioned specification, active predicate process, and multiple language bindings. | Excellent semantic fit. Full protobuf/envelope adoption is unnecessary for this offline TruePanel boundary. | Specifications and implementations are permissively licensed; no schema or code copied. | Adapt typed-subject and monotonic-policy semantics behind a TruePanel schema. |
| in-toto Witness | Policies name trusted functionary keys, required attestations, and Rego conditions. | Mature supply-chain attestation project donated into in-toto. | Strong future shortcut for multi-functionary policy, but adds Go/Rego/DSSE and a larger operational surface than a one-operator offline appraisal needs. | Apache-2.0 ecosystem; adoption would require notices. | Revisit if AEGIS gains multiple independent reviewers or remote attestation storage. |
| Sigstore policy-controller | Verifies that attestations are signed by a trusted authority and satisfy an explicit policy. | Active production project in the Sigstore ecosystem with Kubernetes-oriented deployment and tests. | Sound separation of signature verification and policy evaluation; Kubernetes and transparency-service weight do not fit an offline NAS development gate. | Apache-2.0; no code, policy, or package incorporated. | Adapt the signature-plus-policy split, do not adopt now. |
| OpenSSH SSHSIG | Offline namespace-separated detached signatures using the installed verifier and protected public roster. | Mature, audited, already exercised by TruePanel's negative tests. | Best current fit with no new Python dependency, account, service, or network trust. | OpenSSH's permissive licensing applies to the installed executable; no source copied. | Continue behind the TruePanel-owned verifier interface. |
| OPA / Gatekeeper | Deterministic policy evaluation, decision identity, and testable violation messages. | Mature CNCF policy ecosystem. | Useful if appraisal policy grows dynamic or multi-tenant; Rego/runtime dependency is excessive for four fixed choices and fail-closed fields. | Apache-2.0; no code or Rego incorporated. | Keep as architectural inspiration only. |

### Build versus adopt

TruePanel keeps the small owned appraisal schema and the installed OpenSSH verifier. The domain-specific contract must express dossier subjects, the Recovery Coverage Matrix, HoloDeck measurements, planning-only scope, and explicit negative hardware authority. A general admission controller would add substantial machinery without eliminating those checks.

No external code, schema, package, service, credential, key, dataset, Rego policy, or generated binding was incorporated. The most promising collaboration opportunity is the in-toto Attestation Framework maintainers: a vetted review/appraisal predicate could eventually make this evidence portable without conflating appraisal with authorization.

## Rejected and failed approaches

- **Treat dossier readiness as approval:** rejected because machine completeness cannot represent operator judgment.
- **Reuse the calibration-decision namespace:** rejected because an older decision signature could acquire later-stage appraisal meaning.
- **Name the result “field-checkride approved”:** rejected because it would imply execution authority. The result permits manual planning only.
- **Store one mutable current appraisal:** rejected because replacement would erase the operator's prior HOLD or approval. Receipts are content-addressed and non-replaceable.
- **Adopt Witness, Sigstore policy-controller, or OPA now:** rejected for dependency and operational weight; their separation-of-policy concepts were sufficient for this bounded step.

## Open risks and next gate

- Fixture keys prove the protocol, not JT's identity or judgment.
- One operator cannot provide organizational separation of duties; the receipt records that reality without fabricating a second reviewer.
- Local POSIX custody is not an independently witnessed transparency log or trusted timestamp.
- Planning eligibility is not field validation, accuracy, safety clearance, execution permission, installation readiness, or deployment authority.

The next safe increment is a separately confirmed, read-only field-checkride plan packet containing exact passive observations, privacy constraints, abort criteria, and required verification evidence. It must remain unable to start collection, access BattleStation, or actuate hardware.
