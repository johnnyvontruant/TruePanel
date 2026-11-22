# AEGIS transparency witness continuity

## Outcome

This increment advances the monitor-quorum rehearsal from one shared snapshot
to a stateful checkpoint ratchet. Each of two distinct monitors must bind its
exact prior persisted checkpoint, the next checkpoint, a consecutive state
sequence, and a valid Merkle consistency proof. The state must be declared
persisted before its cosignature is accepted.

The result is deliberately bounded: `TRANSPARENCY_WITNESS_CONTINUITY_REHEARSED`
means the verifier and deterministic state machine behave correctly in
HoloDeck. It does not prove durable production storage or separate operators.
Active runtime validation stays `PENDING`, production eligibility is false,
and every operational authority remains false.

## Architecture

`truepanel.aegis.transparency_witness_continuity` is a TruePanel-owned adapter
between the prior monitor-quorum result and a future C2SP witness service. For
every monitor transition it requires:

- the exact trusted monitor identity, counted once;
- the prior and current canonical checkpoint digests;
- unchanged origin and exact prior/current tree sizes and roots;
- a consecutive `N → N+1` state sequence;
- a valid RFC 9162-shaped consistency proof between those roots;
- `persisted_before_cosignature: true` inside the signed statement;
- a purpose-specific SSHSIG namespace;
- two valid transitions before the continuity quorum passes.

The function is pure and performs no storage or network operation. A real
adapter can later replace the verifier callback and supply state from two
separately operated C2SP witnesses without changing AEGIS policy.

## Measurements

| Measure | Result |
| --- | ---: |
| Deterministic scenarios | 12 |
| Exact two-monitor ratchets accepted | 1 |
| Hold paths | 11 |
| Stale-state, invalid-proof, state-fork acceptances | 0 |
| Persistence-ordering bypasses | 0 |
| Signature-substitution acceptances | 0 |
| Independently operated production monitors | 0 |
| Recovery matrix | 10/10 trusted, 0 gaps |
| Shared-cooling first match | sample 19 |
| Isolated threshold first match | sample 46 |
| Lead | 27 samples |
| Deployments / hardware actions / network calls | 0 / 0 / 0 |

## Prior-Art Field Report

Research and source inspection were refreshed on 2026-11-21.

| Candidate | What it supplies | Maturity, platform fit, and weight | License | Recommendation |
| --- | --- | --- | --- | --- |
| [C2SP tlog-witness v1.0.0](https://c2sp.org/tlog-witness@v1.0.0) | Normative old-size matching, consistency-proof verification, same-size root checks, persistence-before-response, conflict/error behavior, and witness cosignatures. It explicitly identifies the rollback race if checking and persistence are not atomic. | Best wire contract and exact semantic fit. This increment does not expose HTTP and therefore does not claim protocol conformance. | Open specification; no implementation copied. | **Adapt the state-transition rules now; implement a network adapter only after operators exist.** |
| [transparency-dev/witness](https://github.com/transparency-dev/witness) | `witness/witness.go` transactionally reads latest state, rejects stale old sizes and same-size root changes, verifies consistency, persists the cosigned checkpoint, and only then returns signatures. | Active, focused implementation with SQLite and other persistence adapters. Embedding the Go HTTP service would add runtime, database, telemetry, and deployment surfaces prematurely. | Apache-2.0. `README`, `LICENSE`, `go.mod`, `api/http.go`, and `witness/witness.go` inspected. | **Use as the production service candidate; keep TruePanel's verifier replaceable.** |
| [transparency-dev/distributor](https://github.com/transparency-dev/distributor) | Previously collected and served witnessed checkpoints. Its current README now marks the project and public service deprecated because logs directly distribute cosignatures in published checkpoints. | The code carries SQL, gRPC, cloud, Docker, Prometheus, and HTTP dependencies while upstream says the design is obsolete. | Apache-2.0. README, `go.mod`, and license inspected. | **Reject. Do not build or adopt a separate distributor.** |
| [Armored Witness](https://github.com/transparency-dev/armored-witness/blob/main/docs/transparency.md) | Dedicated witness state and keys, append-only verification, countersigning, and public availability of witnessed checkpoints. | Strongest operator-isolation example; requires hardware, firmware trust, provisioning, and an external operating model. | Apache-2.0. No code or firmware incorporated. | **Collaboration target** for defining two separately governed TruePanel witness operators. |
| [Sigsum](https://github.com/sigsum/sigsum-go) | Small public-log ecosystem with witness cosignatures and explicit verifier policy. | Excellent alternate implementation and interoperability reference. Full client/server adoption is unnecessary before a real external log is selected. | BSD-2-Clause. No code copied. | **Retain as an independent comparison implementation.** |

## Build-versus-adopt decision

Build only the narrow offline policy and deterministic fault model. Adopt or
operate the maintained `transparency-dev/witness` service for real stateful
witnessing rather than creating a TruePanel network service. Do not adopt the
deprecated distributor. No third-party code, binary, schema, credential,
service, or runtime dependency was incorporated.

The most promising collaboration is the transparency.dev witness/Armored
Witness community. JT should approach them after selecting a privacy-safe log
entry format and two operators, asking for guidance on independent key custody,
durable checkpoint state, and direct cosignature distribution.

## Failed and rejected paths

- Snapshot quorum alone failed the continuity requirement: two monitors can
  agree on a view without proving either saw a valid append-only transition.
- A caller-supplied old size without the exact prior checkpoint digest was
  rejected because it permits state substitution.
- Cosigning before durable persistence was rejected because concurrent updates
  can roll state backward; this is the race called out by C2SP.
- A separate distributor service was rejected after upstream marked it
  deprecated and obsolete.
- Local ephemeral monitor keys remain simulated operators; they do not satisfy
  production independence.
- Automatic runtime promotion remains forbidden. Witness continuity supplies
  evidence, not deployment, storage, network, or hardware authority.

## Reproduction

```bash
pytest -q tests/test_aegis_transparency_witness_continuity.py
python -m truepanel.holodeck.aegis_transparency_witness_continuity \
  --output /tmp/aegis-witness-continuity.json
diff -u docs/evidence/aegis-transparency-witness-continuity-checkride-v1.json \
  /tmp/aegis-witness-continuity.json
node --check truepanel/web/static/reliability-view.js
python -m truepanel.hangar validate --root .
```

## Production gate

No deployment was performed. The next safe step is a file-backed or service
adapter exercised under crash and concurrent-update fault injection, followed
by two separately operated C2SP witnesses over a privacy-safe external log.
Until durable state and independent operators are evidenced, active-record
continuity and production trust remain `PENDING`.
