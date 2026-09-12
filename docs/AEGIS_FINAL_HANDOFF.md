# AEGIS final handoff seal

Project FINAL HANDOFF closes a time-of-check/time-of-use gap without giving AEGIS
deployment authority. After independent review and the manual promotion gate succeed,
AEGIS re-witnesses the actual staged bytes and issues a content-bound seal valid for at
most five minutes. At handoff it re-witnesses the stage again and verifies the exact
request, receipt, complete gate result, paths, manifest bytes, deployable tree, clock order,
expiry, replay state, and guarded upgrader confirmation contract.

Success is only `READY_FOR_OPERATOR_CONFIRMATION`. The evaluator neither supplies the
confirmation phrase nor calls the upgrader, consumes the seal, writes runtime state,
changes a service, or promotes files. Wiring this seal into the real promotion entry
point is deliberately deferred because that would modify a production-capable boundary
and requires separate operator review.

## Deterministic evidence

HoloDeck experiment `TP-EXP-0028` uses a disposable validated stage. One exact case is
ready; nine cases hold for expiry, clock rollback, replay, request change, receipt
change, gate downgrade, confirmation-contract change, unknown seal fields, and stage
tamper. False-ready decisions, confirmation phrases supplied, seal consumptions,
promotion executions, service changes, and runtime writes are all zero.

The preserved artifact is
[`docs/evidence/aegis-final-handoff-seal-v1.json`](evidence/aegis-final-handoff-seal-v1.json).
Its file SHA-256 is recorded by HANGAR; its canonical evidence digest is
`262c4ba7c4d98e19e5cc26592c90d23978c97036f6a43edcd56878b3b18026d7`.

## Prior-Art Field Report

| Candidate | What transfers | Maturity / fit | License and adoption decision |
| --- | --- | --- | --- |
| [TUF specification](https://theupdateframework.github.io/specification/latest/) | Expiration, rollback/freeze resistance, threshold trust, and content hashes | Mature supply-chain standard; strong semantic fit and zero runtime dependency | Community Specification License 1.0. Adapt the ideas; do not copy code. |
| [Uptane Standard](https://uptane.org/docs/2.1.0/standard/uptane-standard) | Re-check metadata and time immediately before an installation-sensitive operation | Mature automotive update design; its secondary verification boundary closely matches the handoff risk | Specification concepts only; no code incorporated. |
| [SLSA provenance v1.2](https://slsa.dev/spec/v1.2/provenance) | Bind an artifact subject to a cryptographic digest and keep verification distinct from production | Mature, lightweight attestation vocabulary; useful architectural inspiration | Community Specification License 1.0. Adapt subject-binding semantics. |
| [GitHub deployment environments](https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/manage-environments) | Separate protected approval from deployment execution | Well-maintained hosted control, but wrong platform and undesirable external dependency for a local NAS | Inspiration only; do not adopt as the runtime gate. |

The best shortcut remains standards composition, not a new dependency: reuse the
existing TruePanel stage witness and OpenSSH verifier, then apply TUF/Uptane freshness
and replay semantics behind a TruePanel-owned interface. This avoids a new daemon,
hosted service, credential path, or cryptographic library. No external code, schema,
binary, service, key, or notice-bearing artifact was incorporated.

Rejected approaches include a caller-supplied final digest, an unbounded readiness
decision, automatic seal consumption, embedding the human confirmation phrase in an
executor call, and treating the earlier reviewer receipt as proof that later staged
bytes are unchanged. A worthwhile collaboration target is the Uptane community: its
maintainers have the closest operational experience with last-mile, replay-resistant
verification before a safety-sensitive update.

## Safety and integration status

The Recovery Coverage Matrix remains 8/8 trusted with zero gaps. Mission Control is
unchanged because this is short-lived offline handoff evidence, not runtime incident
state. Nothing in this increment accesses a live host, provisions trust material,
signs a receipt, consumes a seal, supplies confirmation, or performs promotion.
