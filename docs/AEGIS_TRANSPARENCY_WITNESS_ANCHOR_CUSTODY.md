# AEGIS threshold recovery-anchor custody

## Outcome

This increment closes the remaining self-authentication gap in the external
recovery anchor. Two distinct governed custodians must now produce valid
purpose-specific SSH signatures over one canonical in-toto-shaped statement
whose subject is the exact SHA-256 anchor digest. The signed predicate also
binds the checkpoint, state sequence, fixed 2-of-2 policy, negative authority
claims, and the dedicated signature namespace.

The verifier first replays the complete anchored two-store recovery contract,
then reconstructs the expected statement rather than trusting statement fields,
and finally counts at most one valid signature from each rostered identity.
Missing, duplicate-identity, duplicate-key, untrusted, substituted, wrong-purpose, rollback,
threshold-downgraded, and authority-escalating evidence fails closed.

`THRESHOLD_ANCHOR_CUSTODY_REHEARSED` is a HoloDeck result. Both keys are
ephemeral fixture keys created and destroyed in one run. It does not establish
separate human operators, an offline publication channel, physical storage
independence, or a physical power cut. Production trust and every operational
authority remain false.

## Architecture and measurements

The TruePanel-owned interface has three replaceable boundaries:

1. `build_anchor_custody_statement()` produces a digest-bound typed statement.
2. `OpenSshSignatureVerifier` checks each identity through a protected roster
   and the dedicated `truepanel-aegis-witness-anchor-custody-v1@truepanel`
   SSHSIG namespace.
3. `evaluate_threshold_anchor_custody()` reconstructs policy, re-verifies the
   recovered stores, deduplicates identities and key fingerprints, enforces 2-of-2, and records a
   content-addressed result.

| Measure | Result |
| --- | ---: |
| Deterministic scenarios | 12 |
| PASS / expected HOLD | 2 / 10 |
| Distinct fixture custodians | 2 |
| Required threshold | 2 of 2 |
| Recovery Coverage Matrix | 15/15 trusted, 0 gaps |
| Missing/duplicate-identity/duplicate-key/untrusted acceptances | 0 |
| Signature/purpose substitution acceptances | 0 |
| Anchor rollback acceptances | 0 |
| Threshold downgrade acceptances | 0 |
| Physical operator-independence validations | 0 |
| Physical power-loss validations | 0 |
| Shared-cooling detection | sample 19 vs threshold 46; 27-sample lead |
| Deployments / hardware actions / network calls | 0 / 0 / 0 |

## Prior-Art Field Report

Research and source inspection were refreshed on 2026-11-25.

| Candidate | What the actual specification/source supplies | Fit, maturity, and dependency weight | License / provenance | Build versus adopt |
| --- | --- | --- | --- | --- |
| [The Update Framework specification v1.0.37](https://theupdateframework.github.io/specification/v1.0.37/) and [python-tuf metadata implementation](https://github.com/theupdateframework/python-tuf/blob/develop/tuf/api/metadata.py) | A role carries authorized key IDs and an explicit positive threshold; one key contributes at most one signature. `Metadata.from_dict()` rejects duplicate key IDs. The specification also recommends offline custody for top-level keys. | Production-stable and actively maintained. Full updater adoption would add `securesystemslib`, download, expiration, delegation, and repository semantics that an offline recovery receipt does not need. | Specification used as architectural reference. python-tuf is MIT OR Apache-2.0. No source copied and no package added. | **Adapt the distinct-key threshold rule; do not embed a software-update framework.** |
| [in-toto Attestation Framework v1.2](https://github.com/in-toto/attestation/blob/main/spec/README.md) and [Statement v1](https://github.com/in-toto/attestation/blob/main/spec/v1/statement.md) | A typed statement binds an immutable subject by digest to an unambiguous predicate type while leaving authentication to a separate envelope. | Smallest interoperable semantic fit. The local JSON shape is intentionally in-toto-compatible at the statement layer, but this increment does not claim DSSE conformance or use its libraries. | Specification/schema idea only; no source, library, or generated schema copied. Repository licensing and attribution must be rechecked before importing code. | **Adapt the statement shape behind a TruePanel interface.** |
| [C2SP tlog-witness v1.1.0](https://c2sp.org/tlog-witness@v1.1.0) | Witnesses maintain the latest consistent checkpoint, verify append-only consistency, persist before returning timestamped cosignatures, and let clients verify self-contained evidence offline. | Exact production direction for external witnesses, but an HTTP witness service and monitoring channel are premature before operators and approved privacy-safe entries exist. | Specifications CC BY 4.0; repository code/data BSD-1-Clause. No text or code incorporated. | **Adopt the protocol when real external operators exist; keep this offline adapter replaceable.** |
| [Sigstore Rekor architecture](https://github.com/sigstore/architecture-docs/blob/main/rekor-spec.md) | A signed checkpoint is the root of trust for inclusion; witnesses must be logically separate from the log and distribute signed commitments. | Mature ecosystem and strong publication model, but Rekor deployment would add network service, PKI, log operations, monitoring, and privacy exposure. | Community Specification license; Sigstore project code is Apache-2.0. No component or schema incorporated. | **Use as publication architecture, not an embedded dependency.** |
| [OpenSSH SSHSIG](https://man.openbsd.org/ssh-keygen.1#Y_sign) | Purpose-specific namespaces, detached signatures, and an allowed-signers policy file using a ubiquitous audited tool already present in TruePanel. | Lowest dependency and implementation risk because the hardened verifier already exists and snapshots a protected roster. | OpenBSD/OpenSSH permissive licenses; only the installed system binary is invoked. | **Adopt now behind the existing verifier interface.** |

### Incorporated shortcut and provenance

The only external behavior exercised is the existing system OpenSSH
`ssh-keygen -Y sign/verify` path. The statement structure adapts the in-toto
subject/predicate separation, and the quorum semantics adapt TUF's unique-key
threshold rule. All policy, canonicalization, recovery verification, evidence,
and tests are newly implemented in TruePanel. No third-party source, package,
binary, key, credential, service, or network dependency was added.

### Rejected and failed approaches

- A second hash next to the anchor was rejected because an attacker replacing
  both stores and the anchor could replace that hash too.
- A 1-of-2 policy was rejected because it does not tolerate one compromised or
  mistaken custody path.
- Counting signatures or names without distinct key fingerprints was rejected
  because aliases and duplicate signatures from one key are not independent evidence.
- Reusing the monitor-signature namespace was rejected as cross-purpose replay.
- Embedding python-tuf was rejected because update roles, downloads,
  expiration, and delegation are outside this receipt's scope.
- DSSE/Rekor services were rejected for now because network publication,
  privacy, PKI, and operator governance are not yet approved.
- Fixture keys were not described as independent production operators.

## Collaboration and production gate

The strongest collaboration opportunity is a joint operating profile with the
TUF, in-toto, and transparency.dev/C2SP maintainers: define a minimal typed
recovery-anchor predicate, offline custodian rotation/revocation, and later
publication as a witnessed checkpoint without coupling TruePanel to one log.

No deployment occurred. The next gate remains two separately governed human
custodians holding keys and the exact envelope outside both witness devices,
plus a recorded controlled physical power cut on the intended filesystem and
storage-controller stack. Until those independent facts exist, production
trust remains false.

## Reproduction

```bash
pytest -q tests/test_aegis_transparency_witness_anchor_custody.py
python -m truepanel.holodeck.aegis_transparency_witness_anchor_custody \
  --output /tmp/aegis-witness-anchor-custody.json
diff -u docs/evidence/aegis-transparency-witness-anchor-custody-checkride-v1.json \
  /tmp/aegis-witness-anchor-custody.json
```
