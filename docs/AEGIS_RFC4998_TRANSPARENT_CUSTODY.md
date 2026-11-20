# AEGIS RFC 4998 transparent custody

## Outcome

AEGIS now has a replaceable verifier for a signed append-only receipt over the
exact timestamped-custody rehearsal evidence. The receipt binds a canonical
entry to an RFC 9162-shaped SHA-256 tree, verifies the entry's inclusion,
verifies append-only growth from a separately signed prior checkpoint, and
authenticates both checkpoints through a protected purpose-specific SSHSIG
roster.

This is a HoloDeck verification rehearsal, not an independently operated log.
The active record remains `PENDING`; production trust and runtime, deployment,
network, storage, and hardware authority remain false.

## Architecture

| Boundary | Contract |
|---|---|
| Entry | Binds the timestamped-custody record ID, custody ID, result digest, exact checkride artifact digest, and `authority: NONE`. |
| Merkle tree | RFC 9162-shaped SHA-256 leaf/node domain separation and deterministic non-power-of-two shape. |
| Inclusion | Recomputes the signed root from the exact entry, index, size, and shortest audit path. |
| Consistency | Proves the current tree extends the separately signed prior tree without rewriting or reordering its prefix. |
| Checkpoints | Both checkpoints require the governed log identity under a purpose-specific SSHSIG namespace. |
| CI | Downloads the same-run timestamp artifact, generates ephemeral log keys, byte-compares reviewed output, and preserves the next artifact. |

## Scenario evidence

Ten deterministic paths produce one signed append-only rehearsal, one explicit
receipt-required state, and eight holds. The Recovery Coverage Matrix remains
8/8 with zero gaps. The fan-degradation shared-cooling diagnosis remains at
sample 19 versus sample 46 for isolated thresholds, a 27-sample lead. No
network call, runtime write, deployment, or hardware action occurs.

## Prior-Art Field Report

Research was refreshed against upstream specifications, source repositories,
dependency manifests, tests, and licenses on 2026-11-19.

| Candidate | Capability and maturity | Platform/dependency/security fit | License / decision |
|---|---|---|---|
| [RFC 9162 Certificate Transparency v2](https://www.rfc-editor.org/rfc/rfc9162) | Normative domain-separated Merkle Tree Hash, compact inclusion proofs, and append-only consistency proofs; widely deployed design lineage. | Small deterministic primitives fit the offline simulator. It does not define AEGIS admission policy, checkpoint key custody, or monitoring operations. | IETF standard. **Adapt the algorithms behind a TruePanel interface.** No source copied. |
| [Tessera](https://github.com/transparency-dev/tessera) | Production-ready tile-backed append-only logs, POSIX/cloud drivers, witness policies, monitoring, migration, and metrics; recommended successor to Trillian. | Strongest future operator shortcut. Its current Go module brings storage SDKs, gRPC, OpenTelemetry, witness policy, database, and cloud dependencies that are disproportionate for an appliance-side verifier. | Apache-2.0 with notice obligations if adopted. **Collaborate/adopt for an external service later; do not embed now.** |
| [Rekor v2 / rekor-tiles](https://github.com/sigstore/rekor-tiles) | Active Sigstore signature-transparency service on Tessera with canonical entries, signed checkpoints, public monitoring, KMS and multiple backends. | Excellent public-verifiability path, but its actual module includes Fulcio, Sigstore bundles, cloud KMS/storage, gRPC, telemetry, and a large transitive graph. Public logging also creates privacy and availability policy decisions. | Apache-2.0. **Defer service adoption; adapt entry/checkpoint separation only.** |
| [SCITT RFC 9943](https://www.rfc-editor.org/rfc/rfc9943) | Separates signed statements, registration policy, transparency receipts, transparent statements, and replay auditing; explicitly requires append-only, non-equivocation, and replayability. | Best semantic model for multiple independent receipts. Full COSE receipt and transparency-service operation would add a second envelope/identity stack before production identities exist. | IETF standard. **Architectural inspiration; retain receipt aggregation as a migration path.** |
| [Trillian](https://github.com/google/trillian) | Mature, production-used general transparency log with inclusion/consistency proofs and application-defined personalities. | Stable but in maintenance mode; upstream recommends Tessera for new operators. gRPC plus database operation is unnecessary for this local checkride. | Apache-2.0. **Reject for new deployment; learn from its personality boundary.** |

### Build-versus-adopt conclusion

The legitimate shortcut for production is Tessera, not a new TruePanel log
service. This increment builds only the narrow verifier and deterministic proof
generator needed to define AEGIS policy and CI contracts. It intentionally does
not implement storage, submission APIs, network transport, checkpoint gossip,
or a production witness. No third-party code, schema, binary, service,
credential, or runtime package was copied or added.

The strongest collaboration opportunity is the transparency-dev Tessera and
Sigstore Rekor v2 maintainers. JT should approach them after privacy policy,
retention, log identity, protected signing keys, and at least two independent
monitor operators are defined, asking whether AEGIS custody entries should use
the standard tlog-tiles and checkpoint formats.

## Failed and deferred approaches

- A local signer is not called an independent witness. Independent
  non-equivocation requires separately operated monitors and checkpoint gossip.
- Embedding Tessera or Rekor v2 was rejected: their actual dependency and
  service surface is justified for an external operator, not this verifier.
- Trillian was rejected for new deployment because upstream recommends Tessera.
- Public logging was rejected until Black Box and custody metadata receive a
  privacy and retention review.
- Inclusion alone was rejected because it cannot prove append-only extension;
  both prior and current signed checkpoints plus a consistency proof are needed.

## Reproduction

```text
pytest -q tests/test_aegis_rfc4998_transparent_custody.py
python -m truepanel.holodeck.aegis_rfc4998_transparent_custody --output /tmp/aegis-transparent-custody.json
python -m truepanel.hangar validate --root .
node --check truepanel/web/static/reliability-view.js
```

## Remaining gate

Select an external transparency operator, define privacy-safe entry contents,
provision governed log and monitor identities, require at least two independent
monitors to gossip signed checkpoints, and register one fresh passive active
record. Until then, independent non-equivocation and runtime trust remain
`PENDING`.
