# AEGIS Recovery Ground Truth

Research and implementation date: 2026-09-02

This increment adds a provider-neutral evidence boundary between recovery
facts and CHECKRIDE clearance. It remains advisory and read-only. A digest can
prove that a statement did not change after issuance; it cannot prove who
issued it. TruePanel therefore validates provider governance, freshness,
incident binding, subject identity, semantic claims, and contradictions as
separate concerns.

## Contract

Each recovery statement binds one incident to one SHA-256-addressed subject
and one typed predicate. The predicate records provider identity and mode,
source reference, observation and expiry, evidence maturity, claims, and the
absence of control authority.

Two statement kinds are required for CHECKRIDE review readiness:

1. `backup.restore-verification`: an independently sourced backup with a
   named restore test, declared scope, fresh observation, and evidence digest;
2. `storage.replacement-candidate`: a passively observed candidate whose
   strong identity digest differs from the source drive, whose capacity is
   sufficient, and whose pool membership and data disposition are safe.

The reconciler fails closed on missing, expired, mutated, mismatched,
ungoverned, ambiguous, or contradictory statements. `EVIDENCE_READY` means
only that the evidence package can proceed to operator review. Physical
service and storage-write authority remain false.

## Prior-art field report

| Candidate | What the actual specification/code supplies | Fit and license | Decision |
| --- | --- | --- | --- |
| [in-toto Statement v1](https://in-toto.io/Statement/v1) | A compact subject/digest/predicate separation that binds claims to identified artifacts. The specification and repository license were inspected. | Excellent semantic fit; Apache-2.0. Pulling the signing stack into the appliance would add key lifecycle and verification weight. | **Adapt the shape**, in original TruePanel code, behind a replaceable interface. Do not claim in-toto conformance or copy source. |
| [W3C PROV-DM](https://www.w3.org/TR/prov-dm/) | Separates entities, generating activities, and responsible agents so provenance can support quality and trust assessments. | Stable open standard; useful vocabulary, but RDF/OWL serialization is unnecessary for two local evidence kinds. | **Use as architectural vocabulary** for subject/provider/observation lineage. No schema or text copied. |
| [Sigstore attestation verification](https://docs.sigstore.dev/cosign/verifying/attestation/) | Demonstrates that integrity, signer identity, policy validation, and missing-attestation behavior are distinct problems. | Mature Apache-2.0 ecosystem, but public transparency services, OIDC, key management, and container-oriented tooling are disproportionate here. | **Defer cryptographic provider authentication.** State explicitly that local SHA-256 is integrity-only and fail closed when provider identity is not governed. |
| [restic repository checks](https://restic.readthedocs.io/en/latest/045_working_with_repos.html) | `check --read-data` and bounded subsets verify repository structure and stored pack data; inspected implementation is tested Go code. | Strong future backup-provider input; BSD-2-Clause. A repository check is not itself an application restore test. | **Future adapter**, requiring a separate restore-test identity and scope. Do not treat backup existence or a successful structural check as recoverability proof. |
| [OpenZFS replacement semantics](https://openzfs.github.io/openzfs-docs/man/master/8/zpool-replace.8.html) | Requires the replacement to be at least the minimum device size and explains why a changed physical disk may retain the same device path. | Canonical platform semantics; CDDL implementation. | **Adapt documented rules only.** Never use `/dev/sdX` as durable identity; no OpenZFS source copied. |
| [GUAC](https://github.com/guacsec/guac) | Normalizes provenance into a graph for policy, audit, and root-cause queries. | Mature idea but a graph database and service stack are excessive for two bounded local statements. Apache-2.0. | **Reject runtime adoption**; retain a small deterministic ledger that can later export lineage. |

No third-party source, binary, library, model, dataset, credential, cloud
service, listener, or notice-bearing artifact was incorporated. The standard
library implementation is replaceable and the project remains MIT licensed.

## HoloDeck proof

`aegis-recovery-ground-truth-v1` exercises one valid and six unsafe paths:

| Path | Expected result |
| --- | --- |
| Fresh incident-bound backup and candidate | `EVIDENCE_READY` |
| Statement changed after issuance | `HOLD` |
| Evidence expired | `HOLD` |
| Candidate reuses source identity | `HOLD` |
| Provider mode is ungoverned | `HOLD` |
| Backup statement absent | `HOLD` |
| Multiple valid backup statements are ambiguous | `HOLD` |

Result: **1/1 valid path ready, 6/6 unsafe paths held, 0 unsafe false-ready
decisions**. The proof is deterministic lab evidence, not field validation.
The preserved artifact is
`docs/evidence/aegis-recovery-ground-truth-v1.json`.

## Mission Control

CHECKRIDE now shows a Ground Truth Evidence section containing accepted,
rejected, and missing statement kinds; provider and mode; evidence maturity;
ledger digest; and the explicit `digest authenticates provider: NO`
disclosure. It stays single-column at 760px and below and uses the existing
shared status stream.

The topbar health annunciators were also hardened before further cockpit
experiments: visible state text removes color-only meaning, non-nominal states
sort first, all pills wrap on phones, and native buttons own keyboard
activation without a duplicate handler.

## Failed and deferred routes

- Treating a SHA-256 digest as proof of provider identity: rejected.
- Treating a repository consistency check as a restore test: rejected.
- Trusting a masked serial suffix as strong replacement identity: rejected.
- Selecting silently between multiple valid statements: rejected; ambiguity
  remains a HOLD.
- Adding Sigstore, GUAC, RDF, or a cloud attestation service now: deferred due
  to dependency, credential, privacy, and operational weight.
- Collecting live evidence during this experiment: not attempted; absence of
  BattleStation access is not a blocker for the interface or HoloDeck proof.

## Reproduction

```console
pytest -q tests/test_aegis_attestations.py tests/test_aegis_attestation_rehearsal.py tests/test_checkride.py
python -c "from truepanel.holodeck.aegis_attestations import run_recovery_attestation_rehearsal as run; print(run()['measurements'])"
node --check truepanel/web/static/reliability-view.js
python -m truepanel.hangar validate --root .
```

## Strongest next step

Implement one passive local backup adapter and one passive block-inventory
adapter that produce these statements from supported TrueNAS interfaces, then
compare their output with the deterministic contract before allowing a real
CHECKRIDE receipt to leave `HOLD`. Provider authentication should be designed
only after the local trust root and key-rotation burden are explicit.
