# AEGIS Airworthiness

Project AIRWORTHINESS is TruePanel's fail-closed assurance layer for deciding whether an accepted AEGIS reliability configuration is still inside its validated operating envelope and whether a proposed successor is ready for an operator-controlled promotion review.

It is deliberately not an automatic deployment system. AIRWORTHINESS can observe, compare, validate, witness, and issue bounded evidence. It cannot install a successor, promote a staged tree, restart services, mutate storage, operate hardware, or approve itself.

## Why it exists

AEGIS now combines several reliability capabilities: correlation, Recovery Coverage Matrix evidence, governed passive TrueNAS observations, stable Lifeline identity, SENTINEL consequence projection, and guided recovery. A green test suite alone is not enough to prove that an accepted reliability configuration remains valid after time passes, the TrueNAS platform changes, or staged bytes differ from the candidate that was reviewed.

AIRWORTHINESS turns those assumptions into explicit, machine-verifiable gates.

## Trust chain

The graduated chain is:

1. **Accepted envelope** records the validated TruePanel version, TrueNAS platform scope, correlation policy, Recovery Coverage Matrix digest, selected runtime subjects, evidence subjects, issue time, and expiry time.
2. **Platform witness** passively reads `system.version` through the governed read-only TrueNAS client and binds the normalized TrueNAS release to the observation. This adds one bounded middleware read and no write authority.
3. **Airworthiness evaluation** compares the live witness, coverage contract, policy, packaged subjects, and time window with the accepted envelope. Drift fails closed to `REVIEW` or `HOLD` rather than being treated as current validation.
4. **Requalification** evaluates a successor envelope after expiry or platform/version drift. A coherent successor can become `READY_FOR_OPERATOR_REVIEW`; it is never automatically accepted or installed.
5. **Independent review receipt** binds an external approval to the exact successor and review bundle. AEGIS cannot create an approval that satisfies its own acceptance gate.
6. **Manual promotion request** binds the candidate, rollback target, nonce, and requested staged tree. Promotion remains an explicit operator action.
7. **Stage witness** re-hashes the actual validated stage and refuses to rely only on an earlier manifest claim. Changed or escaped staged bytes hold the chain.
8. **Offline signature verification** validates OpenSSH signatures against the governed signer roster and AIRWORTHINESS namespace without introducing a network signing dependency.
9. **Two-person ceremony** requires distinct accepted signer identities for the same exact promotion request. Duplicate or mismatched signers fail closed.
10. **Final handoff seal** binds the reviewed request, receipt, and manual gate for a five-minute confirmation window. Replay, expiry, changed stage state, or changed gate state returns `HOLD`.

A final seal means only that the exact reviewed request is ready for an operator confirmation. It does not perform that confirmation or promotion.

## Accepted envelope

The packaged envelope is stored in `truepanel/aegis/assurance_envelope.json` and is included in the installed wheel. The current envelope is intentionally time bounded and platform specific.

Its subject list protects the AEGIS policy, coverage contract, assurance code, platform witness, passive-provider/runtime transport boundary, and recovery guidance contract. Evidence subjects bind the accepted state to preserved deterministic and field-validation evidence.

`load_assurance_envelope()` reads the packaged contract. `evaluate_airworthiness()` returns one of three operator states:

- `CURRENT` means the observed platform and protected subjects remain inside the accepted envelope.
- `REVIEW` means the system lacks enough evidence to claim current validation, such as an unavailable platform witness.
- `HOLD` means a known contract condition failed, including expiry, platform drift, subject drift, coverage drift, policy drift, malformed envelope state, or clock rollback.

No state grants control authority.

## Platform witness and read budget

The governed passive runtime may include a platform witness by issuing one read-only `system.version` query after session-role verification. The established fresh-observation budget therefore becomes four middleware calls when platform witnessing is requested: role verification, platform version, replication evidence, and cloud-backup evidence.

The witness publishes normalized platform facts rather than credentials, transport endpoints, usernames, or other governed connection details. Cached/stale evidence continues to obey the passive runtime's existing fail-closed freshness rules.

## Requalification

Expiry and platform drift do not silently stretch the old envelope. `evaluate_successor_envelope()` requires a successor to bind its predecessor, renewal contract, bounded validity period, platform witness, coverage state, policy, and runtime subjects.

The deterministic requalification rehearsal proves that:

- a coherent same-platform renewal or platform upgrade can reach operator review;
- missing witness evidence remains review-only;
- wrong predecessor, downgrade, overlong validity, automatic acceptance, renewal-contract drift, and runtime-subject drift hold;
- candidate installations, automatic acceptances, and runtime writes remain zero.

## Independent approval and promotion boundary

AIRWORTHINESS separates evidence generation from approval. A successor cannot become promotable merely because AEGIS says its own tests passed.

The review bundle and receipt are content-addressed. The promotion request is also content-addressed and includes rollback identity and a nonce. The staged tree is witnessed again from disk before the gate can clear. Offline signatures are checked against the governed signer roster, and the two-person ceremony requires independent signer fingerprints bound to the same request.

The manual gate can report that the exact candidate is eligible for operator promotion. It does not call the installer or lifecycle promotion path.

## Final handoff

`issue_final_handoff_seal()` is the narrowest point in the chain. It refuses stale or unready prerequisites and produces a short-lived seal. `evaluate_final_handoff()` verifies the seal against the exact current request, receipt, and manual-gate state.

The ready state is `READY_FOR_OPERATOR_CONFIRMATION`. The seal is not a command and is not consumed automatically. The deterministic checkride includes one ready path and nine fail-closed paths covering replay, expiry, unexpected fields, prerequisite drift, and related handoff failures.

## Relationship to Stable Consequence Identity

AIRWORTHINESS is additive to AEGIS Stable Consequence Identity. Stable Consequence Identity preserves proved SENTINEL dependency reach across Linux device-path reassignment by resolving through strong Lifeline identity. AIRWORTHINESS does not replace or weaken that path.

The modern reliability engine keeps consequence correlation intact while evaluating the independent airworthiness contract around the same read-only reliability payload.

## Evidence and executable contract

The preserved proof artifacts live under `docs/evidence/`:

- `aegis-airworthiness-envelope-v1.json`
- `aegis-platform-witness-v1.json`
- `aegis-airworthiness-requalification-v1.json`
- `aegis-independent-review-checkride-v1.json`
- `aegis-manual-promotion-gate-v1.json`
- `aegis-actual-stage-witness-v1.json`
- `aegis-offline-signature-checkride-v1.json`
- `aegis-two-person-ceremony-v1.json`
- `aegis-final-handoff-seal-v1.json`

The focused tests are `tests/test_aegis_assurance.py`, `tests/test_aegis_platform_witness.py`, `tests/test_aegis_requalification.py`, `tests/test_aegis_acceptance.py`, `tests/test_aegis_promotion_gate.py`, `tests/test_aegis_stage_witness.py`, `tests/test_aegis_ssh_verifier.py`, `tests/test_aegis_review_ceremony.py`, and `tests/test_aegis_final_handoff.py`.

CI also builds a fresh wheel and runs `development/tools/smoke_aegis_airworthiness.py` outside the source checkout. That smoke verifies that the packaged envelope, AIRWORTHINESS rehearsal, requalification rehearsal, and final-handoff checkride remain executable after installation.

## Safety invariants

Changes to AIRWORTHINESS must preserve these invariants:

- platform observation stays read-only and bounded;
- credentials, raw connection details, and governed paths are not published;
- stale, missing, ambiguous, mismatched, or malformed evidence cannot become approval;
- AEGIS cannot sign or approve its own successor;
- staged bytes are witnessed independently of an earlier manifest claim;
- independent signatures must bind the same exact promotion request;
- promotion remains manual and rollback-aware;
- a final handoff seal is short lived, replay resistant, and has no execution authority;
- recovery alerts, evidence, and guidance remain visible when AIRWORTHINESS is in `REVIEW` or `HOLD`;
- Stable Consequence Identity and other accepted AEGIS reliability evidence are not weakened to satisfy the assurance layer;
- production mutation and hardware/storage control authority remain false.

Git history preserves the individual research branches and experiments that produced this chain. The maintained product contract is this consolidated AIRWORTHINESS implementation and its executable evidence.
