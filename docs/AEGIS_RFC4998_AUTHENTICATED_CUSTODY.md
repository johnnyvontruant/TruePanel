# AEGIS RFC 4998 authenticated custody

## Outcome

AEGIS now has a bounded, replaceable interface for authenticating who admitted
one exact dual-oracle RFC 4998 receipt into a read-only custody chain. The gate
reconstructs a canonical statement from the record manifest, both oracle
receipt digests, custody identity, sequence, source, validity window, and every
authority denial. It accepts the rehearsal only when a protected OpenSSH
allowed-signers snapshot verifies a detached Ed25519 SSHSIG under the dedicated
`truepanel-aegis-rfc4998-custody-v1@truepanel` namespace.

The signer cannot promote the record. A successful result is
`AUTHENTICATED_CUSTODY_REHEARSED`; the active runtime record remains `PENDING`
and production, deployment, runtime, network, storage, and hardware authority
remain false.

## Architecture

| Boundary | Contract |
|---|---|
| Dual-oracle receipt | Must be the reviewed v1 aggregate, identify the same manifest record and subjects, and retain every authority denial. |
| Custody event | Names one custodian, one read-only HoloDeck Black Box export, sequence 1, no predecessor, a deterministic simulation clock, and a maximum 15-minute validity window. |
| Canonical statement | Binds manifest SHA-256, aggregate receipt SHA-256, both canonical oracle receipt hashes, record subjects, custody metadata, time window, and zero authority. |
| Signature adapter | Uses the existing TruePanel-owned `OpenSshSignatureVerifier`; it snapshots a protected exact-principal Ed25519 roster, rejects symlinks and unsafe permissions, and invokes `ssh-keygen -Y verify` through memory-backed files. |
| HoloDeck | Generates ephemeral keys outside repository evidence and exercises ten deterministic scenarios. No private key, credential, or reusable signature is preserved. |
| CI | Downloads the aggregate receipt produced earlier in the same workflow, runs the real SSHSIG checkride, byte-compares reviewed evidence, and uploads the checkride artifact. |

## Scenario evidence

Ten deterministic scenarios produce one authenticated rehearsal, one explicit
signature-required state, and eight fail-closed holds. Corrupt and foreign
signatures, a wrong namespace, receipt mutation after signing, expired or
future custody, subject mismatch, and authority escalation all fail. The
Recovery Coverage Matrix stays 8/8 with zero gaps, and the shared-cooling
scenario retains its 27-sample lead (sample 19 versus isolated threshold 46).

## Prior-Art Field Report

Research was refreshed against upstream specifications, documentation, source
repositories, and licensing on 2026-11-17.

| Candidate | What it supplies | Maturity / fit | License and weight | Decision |
|---|---|---|---|---|
| [OpenSSH SSHSIG](https://man.openbsd.org/ssh-keygen.1) | Detached signatures, explicit namespaces, exact allowed-signers principals, Ed25519 support, and an installed verifier. | Mature, already used throughout AEGIS, testable offline, and directly addresses signer authentication without a service. | OpenSSH portable licensing; already a platform dependency; no code copied. | **Adopt through the existing TruePanel interface.** Use a new purpose-specific namespace and protected one-principal roster. |
| [in-toto Attestation Framework v1.2](https://github.com/in-toto/attestation/blob/main/spec/README.md) | Separate envelope, statement, predicate, and bundle layers; digest-bound immutable subjects; recognized-attester validation. | Excellent conceptual match and an active CNCF ecosystem. Full DSSE bindings add serialization and dependency surface without improving this offline single-signer rehearsal. | Apache-2.0 software; specification attribution recorded; zero imported code. | **Adapt the layer separation.** Keep TruePanel JSON and SSHSIG now; retain a migration path to DSSE. |
| [Sigstore bundle 0.3](https://docs.sigstore.dev/about/bundle/) | Portable verification material, DSSE or message signatures, transparency entries, and RFC 3161 timestamp evidence for offline verification. | Strongest future portable-custody shortcut. Public-instance identity, Fulcio/Rekor policy, root distribution, and protobuf bindings are premature for a HoloDeck-only gate. | Apache-2.0 ecosystem; materially heavier trust and operational surface. | **Defer.** Reconsider when a production attester identity, protected key custody, and public/private transparency policy exist. |
| [IETF SCITT architecture](https://datatracker.ietf.org/wg/scitt/documents/) | Signed statements registered into verifiable data structures with portable receipts and registration policy. | RFC 9943 is a strong accountability model, while receipt profiles and APIs continue to evolve. A transparency service would not authenticate today’s local custodian by itself. | IETF specification; implementation and service choice deferred. | **Architectural inspiration only.** Keep sequence and predecessor fields so a later transparency receipt can be attached. |
| [SPIFFE/SPIRE](https://spiffe.io/docs/latest/spire-about/spire-concepts/) | Node and workload attestation, short-lived SVIDs, selectors, trust domains, and automated workload identity. | Production-ready for distributed services, but disproportionate for one offline TruePanel process and unable to attest the physical origin of a copied evidence file without deployment-specific selectors. | Apache-2.0; server, agents, plugins, rotation, and trust-domain operations are substantial. | **Reject for this increment.** Revisit only if AEGIS becomes a distributed preservation service. |

### Build-versus-adopt conclusion

The legitimate shortcut is not a new library: it is the mature SSHSIG mechanism
already behind TruePanel's hardened verifier. A new narrow statement builder and
policy evaluator were required because none of the candidates defines
TruePanel's record profile, dual-oracle digest set, custody sequence, 15-minute
window, or zero-authority invariant. No third-party source, schema, credential,
key, fixture, service, or runtime package was copied or added.

The strongest collaboration opportunity is with the in-toto attestation and
Sigstore bundle maintainers. JT should approach them after a real preservation
identity and offline root-custody procedure exist, asking whether this statement
should migrate to a standard DSSE predicate and Sigstore bundle without losing
multi-signature or RFC 3161 evidence.

## Failed and deferred approaches

- A signer-asserted timestamp was rejected as proof of signing time. This
  increment enforces only a bounded simulation window; independent RFC 3161
  evidence is still required for production custody.
- Embedding a reusable test private key or reviewed signature was rejected.
  HoloDeck creates ephemeral keys and preserves only deterministic outcomes.
- Sigstore public services, SCITT registration, and SPIRE agents were rejected
  because they add network, credential, identity-provider, or daemon authority
  before TruePanel has an approved production attester.
- The successful fixture is not called a real active record. It proves the
  verification path over a HoloDeck Black Box export rehearsal only.

## Reproduction

```text
pytest -q tests/test_aegis_rfc4998_authenticated_custody.py tests/test_aegis_rfc4998_active_receipt.py
python -m truepanel.holodeck.aegis_rfc4998_authenticated_custody --output /tmp/aegis-custody.json
python -m truepanel.hangar validate --root .
node --check truepanel/web/static/reliability-view.js
```

## Remaining gate

Provision an actual preservation custodian in the governed roster, capture a
fresh sanitized Black Box EvidenceRecord through a passive read-only handoff,
obtain fresh dual-oracle receipts, and attach independent RFC 3161 signing-time
evidence. Until that checkride exists, runtime active-record custody and
production trust remain `PENDING`.
