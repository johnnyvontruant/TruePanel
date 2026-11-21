# AEGIS transparency monitor quorum

## Outcome

This increment closes the next simulated non-equivocation gap after the signed
append-only RFC 4998 custody receipt. Two distinct rostered monitors must sign
the exact same checkpoint observation before the rehearsal reports
`TRANSPARENCY_MONITOR_QUORUM_REHEARSED`. A single signer, duplicate identity,
untrusted identity, altered checkpoint digest, bad signature, split root, stale
tree size, or authority escalation remains `HOLD`.

This is deliberately not a production trust claim. Both monitor keys are
ephemeral HoloDeck keys created in one process. The result says
`SIMULATED_NOT_PRODUCTION_PROVEN`, the active runtime record stays `PENDING`,
and every operational authority stays false.

## Architecture

`truepanel.aegis.transparency_monitor_quorum` is a narrow, replaceable policy
boundary. It accepts the prior transparent-custody result, one checkpoint, a
set of signed observations, and a verifier callback. The gate requires:

- the prior signed checkpoint, inclusion proof, and append-only proof;
- a valid two-of-two policy over two distinct identities;
- one canonical checkpoint digest, origin, tree size, and root across monitors;
- a purpose-specific SSHSIG namespace and protected exact-principal roster;
- no production, runtime, deployment, hardware, network, or storage authority.

The HoloDeck checkride covers ten paths: one accepted quorum and nine holds.
CI downloads the same-run transparent-custody artifact, reproduces the checkride
byte for byte, and preserves the result as a separate artifact.

## Measurements

| Measure | Result |
| --- | ---: |
| Deterministic scenarios | 10 |
| Exact two-monitor quorum accepted | 1 |
| Hold paths | 9 |
| Split-view acceptances | 0 |
| Duplicate-identity acceptances | 0 |
| Checkpoint/signature substitution acceptances | 0 |
| Independently operated production monitors | 0 |
| Recovery matrix | 9/9 trusted, 0 gaps |
| Shared-cooling first match | sample 19 |
| Isolated threshold first match | sample 46 |
| Lead | 27 samples |
| Deployments / hardware actions / network calls | 0 / 0 / 0 |

## Prior-art field report

Research and code inspection were refreshed on 2026-11-20.

| Candidate | What the code or documentation supplies | Maturity, fit, and weight | License | Decision |
| --- | --- | --- | --- | --- |
| [transparency-dev/witness](https://github.com/transparency-dev/witness) | `witness/witness.go` verifies the log signature, tracks one checkpoint per origin, verifies consistency from stored state, rejects stale or same-size/different-root views, and countersigns accepted checkpoints. The repository implements the C2SP `tlog-witness` API and OmniWitness. | Direct semantic fit and active maintenance, but embedding its Go HTTP service, SQLite persistence, OpenTelemetry, Kubernetes logging, and format/merkle modules would duplicate the current offline boundary. | Apache-2.0; inspected `LICENSE`, `go.mod`, `witness/witness.go`, and API docs. | **Adapt now**, do not import. Keep its feeder/service model as the production path. |
| [Sigsum policy](https://github.com/sigsum/sigsum-go/blob/main/doc/policy.md) | Defines known logs, named witness keys, nested groups, and `k`-of-`n`, `any`, or `all` quorum rules; duplicate witness keys and duplicate group paths are forbidden. | Excellent policy model with explicit operator groups. Full recursive policy syntax is unnecessary for the first two-monitor gate. | BSD-2-Clause for `sigsum-go`; documentation provenance retained. | **Adapt the distinct-identity threshold rule** behind a TruePanel-owned interface. |
| [Sigstore Rekor Monitor](https://github.com/sigstore/rekor-monitor) | Verifies log immutability/append-only behavior and can monitor identities, with reusable GitHub Actions workflows. | Strong operational reference for external monitoring. Rekor-specific entry and certificate handling do not help this local checkpoint-verification unit. | Apache-2.0. No code copied. | **Use later as an external comparison monitor** if Rekor is selected. |
| [C2SP tlog-witness](https://c2sp.org/tlog-witness) | Standard checkpoint submission, consistency proof, and witness cosignature exchange. | Best future wire boundary. This increment has no external witness endpoint and therefore does not claim protocol conformance. | Specification; no implementation copied. | **Target for a future adapter**, after real independent operators exist. |
| [Armored Witness](https://github.com/transparency-dev/armored-witness) | Demonstrates witness keys and state isolated in dedicated hardware and public checkpoint distribution. | Strongest independence model, but hardware procurement, firmware trust, and external operation are beyond this simulated increment. | Apache-2.0 repository. No code or firmware added. | **Most promising collaboration opportunity:** discuss operating two TruePanel log witnesses with the transparency.dev community. |

No third-party code, binary, schema, service, key, credential, or runtime
dependency was incorporated. The implementation is original MIT-licensed
TruePanel code informed by the public protocols above. The existing OpenSSH
adapter is reused through a callback, so a future C2SP witness or Sigsum verifier
can replace it without changing the quorum gate.

## Rejected and failed paths

- Counting two signatures from the same identity failed the independence goal;
  duplicate identities are rejected before threshold evaluation.
- Comparing only root hashes was rejected because origin and tree size are part
  of the checkpoint view and a stale-size fork must be visible.
- Calling two locally generated keys independent was rejected. The UI and
  evidence say simulated operators and production independence zero.
- Importing the Go witness service was rejected for this increment because it
  adds persistence, HTTP, telemetry, and deployment surfaces before external
  operation is approved.
- A one-of-two policy was rejected for the rehearsal because it would not expose
  loss or disagreement of either planned operator.
- Automatically promoting an active record after quorum was rejected. Quorum is
  evidence for non-equivocation, not deployment or hardware authority.

## Reproduction

```bash
pytest -q tests/test_aegis_transparency_monitor_quorum.py
python -m truepanel.holodeck.aegis_transparency_monitor_quorum \
  --output /tmp/aegis-monitor-quorum.json
diff -u docs/evidence/aegis-transparency-monitor-quorum-checkride-v1.json \
  /tmp/aegis-monitor-quorum.json
node --check truepanel/web/static/reliability-view.js
python -m truepanel.hangar validate --root .
```

## Production gate

No deployment was performed. The next safe step is to commission two separately
operated monitors, provision independently governed public keys, persist each
monitor's prior checkpoint, exchange C2SP consistency proofs, and rehearse
checkpoint gossip across a real external log without exposing private Black Box
content. Only then can operator independence move beyond `PENDING`.
