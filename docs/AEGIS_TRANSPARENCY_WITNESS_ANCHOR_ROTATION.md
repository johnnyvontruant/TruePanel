# AEGIS custodian-root rotation

## Outcome

This increment adds continuity for the offline trust root that authenticates a
witness recovery anchor. A proposed custodian-root version N+1 is accepted only
when it is content-addressed, names exactly the approved successor roster,
preserves a 2-of-2 threshold, points to the exact version N root, binds the same
recovery-anchor custody statement and exact predecessor evidence digest, and carries valid threshold approval from
both the current and proposed rosters.

The transition replaces fixture custodian alpha with fixture custodian charlie
while retaining bravo as a bridge identity. Three distinct ephemeral Ed25519
keys participate. This is a deterministic HoloDeck ceremony, not proof of
separate people, hardware tokens, offline media, publication availability,
revocation response, or physical storage behavior. Production trust and every
operational authority remain false.

## Architecture and measurements

The TruePanel-owned boundary provides:

1. `build_custodian_root()` for a content-addressed versioned roster bound to
   the exact anchor-custody statement.
2. `build_rotation_statement()` for a purpose-specific typed N-to-N+1
   transition.
3. `evaluate_custodian_root_rotation()` for fixed old/new policies, consecutive
   versioning, predecessor continuity, distinct fingerprints, dual thresholds,
   and negative authority enforcement.
4. `OpenSshSignatureVerifier` as the replaceable cryptographic adapter using a
   protected allowed-signers snapshot and dedicated SSHSIG namespace.

| Measure | Result |
| --- | ---: |
| Deterministic scenarios | 16 |
| PASS / expected HOLD | 2 / 14 |
| Distinct fixture keys | 3 |
| Required approval | current 2-of-2 plus next 2-of-2 |
| Version transition | 1 to 2 |
| Recovery Coverage Matrix | 18/18 trusted, 0 gaps |
| Missing/duplicate/untrusted quorum acceptances | 0 |
| Signature/purpose substitution acceptances | 0 |
| Rollback/version-skip acceptances | 0 |
| Threshold-downgrade acceptances | 0 |
| Predecessor-substitution acceptances | 0 |
| Physical operator-independence validations | 0 |
| Physical power-loss validations | 0 |
| Shared-cooling detection | sample 19 vs threshold 46; 27-sample lead |
| Deployments / hardware actions / network calls | 0 / 0 / 0 |

## Prior-Art Field Report

Research and source inspection were refreshed on 2026-11-26.

| Candidate | What it supplies | Fit, maturity, and dependency weight | License / provenance | Recommendation |
| --- | --- | --- | --- | --- |
| [The Update Framework specification](https://theupdateframework.github.io/specification/latest/) and [python-tuf updater](https://github.com/theupdateframework/python-tuf/blob/develop/tuf/ngclient/updater.py) | Root N+1 must be signed by thresholds from both root N and root N+1, use unique keys, advance exactly one version, persist before continuing, and reject rollback/freeze. | Exact continuity model. Full adoption would add update download, expiry, delegation, and repository semantics unrelated to this offline receipt. | Specification reference only. python-tuf is MIT OR Apache-2.0. No source copied or dependency added. | **Adapt the dual-threshold consecutive-root invariant.** |
| [Sigstore root-signing](https://github.com/sigstore/root-signing) | Named keyholders, signing-event pull requests, hardware-held personal keys, staging, automated client tests, and publication only after tests. | Strongest operational ceremony model and actively used, but its hosted TUF pipeline and public service are disproportionate before TruePanel has real custodians. | Apache-2.0. No scripts, workflow, metadata, or code copied. | **Adapt ceremony roles and staging later; do not embed.** |
| [Uptane Standard 2.1.0](https://uptane.org/docs/latest/standard/uptane-standard) | Root metadata distributes role keys, thresholds, and revocations; independent Director/Image verification adds resilience to compromise. | Mature safety-oriented profile, but automotive ECU roles and repositories add substantial unrelated machinery. | Standard used as architectural reference; no code incorporated. | **Use as compromise-recovery inspiration, not a dependency.** |
| [Notary Project trust-store policy](https://github.com/notaryproject/specifications/blob/main/specs/trust-store-trust-policy.md) | Named out-of-band trust stores, exact policy selection, fail-closed absence, timestamps, and revocation evaluation. | Useful policy-separation reference; X.509/OCI and online revocation paths do not fit the current SSHSIG envelope. | CNCF Community Specification License 1.0; no schema or code copied. | **Retain exact policy selection; reject direct integration.** |
| [OpenSSH SSHSIG](https://man.openbsd.org/ssh-keygen.1#Y_sign) | Detached signatures, dedicated namespaces, and exact-principal allowed-signers files using the already hardened local adapter. | Lowest dependency and replacement cost. | OpenBSD/OpenSSH permissive licensing; installed system behavior only. | **Continue using behind the TruePanel interface.** |

### Incorporated shortcut and provenance

The implementation adapts TUF's dual-threshold, exactly-consecutive root
continuity rule and Sigstore's separation of current keyholders, proposed
changes, staging, and verification. Only the existing system OpenSSH signing
behavior is executed. All roots, statements, policy evaluation, fixtures,
evidence, tests, and CI contracts are new TruePanel code. No third-party source,
package, binary, schema, key, credential, hosted service, or network path was
incorporated.

### Rejected and failed approaches

- New-roster-only approval was rejected because a substituted trust root could
  authorize itself.
- Current-roster-only approval was rejected because the successor keys would
  never prove possession before activation.
- Version jumps and same-version replacement were rejected because they break
  an auditable chain and enable rollback or mix-and-match ambiguity.
- Threshold reduction during rotation was rejected as silent security-policy
  weakening.
- Counting names without distinct public-key fingerprints was rejected.
- Reusing the anchor-custody namespace was rejected as cross-purpose replay.
- Full python-tuf, Sigstore root-signing, Uptane, and Notary integrations were
  rejected as excessive operational and dependency weight for this boundary.
- Ephemeral fixture keys were not described as real independent custodians.

## Collaboration and production gate

The most promising collaboration is with TUF and Sigstore root-signing
maintainers to define a small recovery-anchor keyholder ceremony: conductor and
verifier roles, hardware-token enrollment, consecutive publication, loss and
compromise procedures, and an independently mirrored root history.

No deployment occurred. The next gate is a recorded ceremony with two
separately governed current custodians and two proposed custodians using
hardware-backed offline keys, publication of every consecutive root outside
both witness devices, a loss/revocation drill, and controlled physical power-cut
recovery on the intended filesystem and storage-controller stack. Until then,
production trust remains false.

## Reproduction

```bash
pytest -q tests/test_aegis_transparency_witness_anchor_rotation.py
python -m truepanel.holodeck.aegis_transparency_witness_anchor_rotation \
  --output /tmp/aegis-witness-anchor-rotation.json
diff -u docs/evidence/aegis-transparency-witness-anchor-rotation-checkride-v1.json \
  /tmp/aegis-witness-anchor-rotation.json
```
