# Project TWO-PERSON CEREMONY

Project TWO-PERSON CEREMONY closes the gap between a witnessed upgrade stage
and two genuinely independent operator reviews. It packages the exact public
facts each reviewer must inspect, narrows OpenSSH trust configuration to an
auditable profile, assembles detached signatures, and still stops before the
manual promotion confirmation.

## Review packet and trust contract

The portable packet contains the canonical acceptance statement, the complete
candidate envelope, appraisal, predecessor envelope, witnessed promotion
request, and reviewer trust policy. SHA-256 bindings cover the statement,
every subject, and the policy. The packet explicitly carries no private key,
signing authority, or promotion authority.

TruePanel accepts only a strict subset of OpenSSH `allowed_signers`: one exact
reviewer identity and one `ssh-ed25519` public key per line. Wildcards,
comma-separated aliases, certificate-authority/options syntax, duplicate
identities, missing reviewers, extra reviewers, invalid Base64, and policy
roster drift fail closed. Comments remain permitted because they are not trust
semantics. The file must also satisfy the protected-file rules from Project
OFFLINE SIGNATURE.

Each reviewer receives the same content-addressed packet, confirms its digest,
reviews the visible subjects, and signs only the canonical statement using the
fixed `truepanel-aegis-review-v1@truepanel` SSHSIG namespace. TruePanel merely
assembles and verifies the detached signatures. It provides no signer and
stores no production private key.

## HoloDeck checkride

The deterministic checkride creates an actual disposable validated stage and
two isolated disposable signing lanes. One exact two-person ceremony reaches
`READY_FOR_MANUAL_PROMOTION`. Eight adversarial paths HOLD: wildcard principal,
principal alias, extra roster identity, certificate-authority option, statement
digest tamper, visible subject tamper, displayed policy tamper, and one signing
lane.

The checkride supplies no promotion confirmation, consumes no receipt, invokes
no promotion, changes no service, and performs no production write. Preserved
evidence is in
[`evidence/aegis-two-person-ceremony-v1.json`](evidence/aegis-two-person-ceremony-v1.json).

## Prior-Art Field Report

- **OpenSSH SSHSIG and allowed signers — adopt behind TruePanel's interface.**
  OpenSSH already supplies detached signatures, required application
  namespaces, signer identities, allowed-signers files, and revocation hooks.
  It is mature, already available on the target platform, carries no new Python
  dependency, and saves a custom cryptographic implementation. Its flexible
  wildcard/options grammar is intentionally constrained by TruePanel's parser.
  OpenSSH is BSD-licensed; no source code was copied.
- **TUF threshold roles — adapt the idea.** TUF's role thresholds and metadata
  binding reinforce two distinct keys and expiring review material. The AEGIS
  packet is not TUF metadata and does not copy its schemas or code. TUF's
  specification is openly published; no notice-bearing artifact was included.
- **NIST SP 800-53 separation of duties — adapt the control objective.** AC-5
  and CM-5 support separating approval from execution and requiring distinct
  roles for sensitive changes. AEGIS keeps review, signing, and the final
  operator promotion act separate. No NIST text or implementation was copied.
- **Sigstore/Cosign — defer.** Identity transparency and keyless workflows are
  promising, but introduce network availability, privacy, identity-provider,
  transparency-log, and trust-root choices that are disproportionate for the
  current offline NAS gate.
- **Minisign/signify — reject for this increment.** They are lightweight, but
  would add another verifier and key lifecycle without improving the already
  platform-native SSHSIG seam or its fixed application namespace.

The best collaboration target remains the OpenSSH project for format and
compatibility guidance; no maintainer contact was made. No external code,
schema, dependency, service, credential, key, or hosted system was incorporated.

## Reproduction

```console
pytest -q tests/test_aegis_review_ceremony.py tests/test_aegis_ssh_verifier.py
python -c "from truepanel.holodeck.aegis_two_person_ceremony import run_two_person_ceremony_checkride as run; print(run())"
python -m truepanel.hangar validate --root .
python development/tools/smoke_installed_wheel.py
```

The remaining field gate is operator-owned provisioning of two independent
public keys and a protected roster, followed by a read-only checkride against a
real validated stage. Promotion remains a separate, explicitly confirmed act.
