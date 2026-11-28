# AEGIS custodian compromise recovery

## Outcome

This increment closes the liveness gap exposed by the prior 2-of-2 custodian
root: losing either key before a rotation makes the quorum unavailable. The
safe path is therefore proactive. HoloDeck first rotates version 2 from 2-of-2
to version 3 with a 2-of-3 roster, with both old and new thresholds approving
the change. It then simulates one custodian becoming compromised and
unavailable, revokes that identity and fingerprint, and rotates to version 4
using two unaffected version-3 custodians plus a valid version-4 quorum.

The compromise path never accepts a signature from the revoked key. Loss before
expansion remains a deliberate HOLD rather than a fictional break-glass bypass.
All identities and Ed25519 keys are temporary fixtures. Production trust,
operator independence, deployment, hardware, network, storage, and runtime
authority remain false.

## Architecture and measurements

The TruePanel-owned boundary adds:

1. a purpose-specific compromise-recovery statement binding the exact
   predecessor evidence, versions 2/3/4, three content-addressed roots, revoked
   identity and fingerprint, and revocation-effective version;
2. a proactive expansion contract requiring current and expanded thresholds;
3. a recovery contract requiring an unaffected current threshold and successor
   proof of possession while excluding the revoked signer; and
4. deterministic negative coverage for premature loss, compromised signing,
   quorum failures, substitutions, version/predecessor faults, downgrade, and
   authority escalation.

| Measure | Result |
| --- | ---: |
| Deterministic scenarios | 18 |
| PASS / expected HOLD | 3 / 15 |
| Roster path | 2-of-2 → 2-of-3 → 2-of-3 |
| Failure tolerance | 0 → 1 → 1 unavailable key |
| Consecutive versions | 2 → 3 → 4 |
| Distinct fixture keys | 4 |
| Recovery Coverage Matrix | 21/21 trusted, 0 gaps |
| Loss-before-expansion acceptances | 0 |
| Revoked-key post-revocation acceptances | 0 |
| Missing/duplicate/untrusted quorum acceptances | 0 |
| Substitution/downgrade/authority acceptances | 0 |
| Physical operator-independence validations | 0 |
| Physical power-loss validations | 0 |
| Shared-cooling detection | sample 19 vs threshold 46; 27-sample lead |
| Deployments / hardware actions / network calls | 0 / 0 / 0 |

## Prior-Art Field Report

Research and actual source/documentation inspection were refreshed on
2026-11-27.

| Candidate | What it teaches or supplies | Capability, maturity, fit, and weight | License / provenance | Recommendation |
| --- | --- | --- | --- | --- |
| [The Update Framework specification](https://theupdateframework.github.io/specification/latest/) | If fewer than a threshold of root keys are compromised, revoke them through a normal consecutive root rotation; threshold compromise requires out-of-band recovery. Root N+1 must be accepted by both old and new policies. | Exact safety model and mature specification. Full repository/update machinery remains unnecessary for this offline anchor receipt. | Specification reference; no code or schema copied. Reference implementations are permissively licensed. | **Adapt proactive threshold-preserving rotations and explicitly hold after quorum loss.** |
| [Sigstore root-signing orchestration](https://github.com/sigstore/root-signing/blob/main/playbooks/ORCHESTRATION.md) and [repository operation](https://github.com/sigstore/root-signing) | Five hardware keyholders with a 3-of-5 threshold, explicit key removal, staged metadata, signing-event PRs, preproduction client tests, and publication only after validation. The playbook still notes disaster recovery as a TODO. | Strongest real operational ceremony reference and actively maintained. Its hosted TUF/KMS/GitHub pipeline is too heavy before TruePanel has governed custodians. | Apache-2.0. Documentation and code inspected; none copied or linked at runtime. | **Adapt expansion-before-loss, staging, keyholder review, and test-before-publication; do not embed.** |
| [NIST SP 800-57 Part 1 Rev. 5](https://doi.org/10.6028/NIST.SP.800-57pt1r5) | Compromised keys must cease applying protection, be revoked, be replaced with new keys, and retain transition metadata for audit. A compromise-recovery plan must identify people, re-keying, inventory, checking, monitoring, and notification. | Authoritative lifecycle guidance, not a software component. It materially strengthens the explicit no-compromised-signing invariant. | U.S. Government publication used as guidance; no code or normative profile incorporated. | **Adopt the lifecycle invariants and retain evidence; do not claim NIST conformance.** |
| [Sigstore threat model](https://docs.sigstore.dev/about/threat-model/) | A threshold root can revoke compromised service trust; a 3-of-5 root makes one key compromise insufficient. | Useful system-level rationale and consistent with Sigstore operations. It does not solve TruePanel's physical custodian governance. | Documentation reference; Sigstore projects are Apache-2.0. | **Use as architecture validation, not a dependency.** |
| [Uptane Standard 2.1.0](https://uptane.org/docs/latest/standard/uptane-standard) | Unique-key threshold verification and root-distributed revocation policy for safety-sensitive systems. | Mature automotive profile, but Director/Image repositories and ECU semantics are unrelated dependency weight. | Standard reference only; no code incorporated. | **Retain as safety inspiration; reject integration.** |
| System OpenSSH SSHSIG | Existing detached Ed25519 signing, purpose namespace, and protected allowed-signers snapshots behind the TruePanel verifier interface. | Lowest dependency and replacement cost. | Existing OpenSSH installation; permissive licensing. | **Continue using only in HoloDeck fixtures.** |

### Incorporated shortcut and provenance

The implementation adapts TUF's consecutive dual-threshold invariant,
Sigstore's proactive multi-keyholder ceremony shape, and NIST's rule that a
compromised signing key must not apply new protection. All policy, statements,
fixtures, evidence, tests, and UI contracts are new TruePanel code. No external
source, package, schema, binary, key, credential, service, or network path was
incorporated.

### Rejected and failed paths

- A 2-of-2 emergency rotation after one key is lost was rejected: there is no
  valid current quorum, so the only honest result is HOLD.
- Accepting a compromised key merely to sign its own revocation was rejected.
- A new roster authorizing itself without the previous threshold was rejected.
- Lowering the threshold to restore availability was rejected as a silent
  security downgrade.
- Keeping the revoked fingerprint under a different identity was rejected.
- A standing universal break-glass key was rejected because it creates a
  single catastrophic authority and an unclear governance path.
- Full TUF, Sigstore, Uptane, HSM, or cloud-KMS integration was rejected as
  premature dependency and operational weight.
- Fixture isolation was not described as separate people, devices, or real
  compromise recovery.

## Collaboration and remaining gates

The strongest collaboration opportunity remains the TUF and Sigstore
root-signing maintainers: ask them to review a small recovery-anchor ceremony
that expands to at least a 2-of-3 hardware-backed roster before production,
records a loss/revocation drill, and mirrors every consecutive root outside the
witness devices.

No deployment occurred. The next gate is that real ceremony, followed by a
controlled physical power-cut recovery on the intended filesystem and storage
controller. Until then, the active record stays pending and production trust is
false.

## Reproduction

```bash
pytest -q tests/test_aegis_transparency_witness_custodian_recovery.py
python -m truepanel.holodeck.aegis_transparency_witness_custodian_recovery \
  --output /tmp/aegis-witness-custodian-recovery.json
diff -u docs/evidence/aegis-transparency-witness-custodian-recovery-checkride-v1.json \
  /tmp/aegis-witness-custodian-recovery.json
```
