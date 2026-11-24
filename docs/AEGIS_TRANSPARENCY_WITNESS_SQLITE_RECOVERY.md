# AEGIS isolated SQLite witness recovery

## Outcome

This increment moves the witness durability rehearsal from one file-backed
adapter to two separately rooted SQLite stores. Each store binds one monitor
identity, retains the exact committed transition and response signature, uses
transactional predecessor comparison, and recovers after an abrupt child-process
`SIGKILL`. A quorum is accepted only when both healthy stores recover the same
checkpoint digest and state sequence.

The result remains deliberately bounded. `ISOLATED_WITNESS_SQLITE_RECOVERY_REHEARSED`
means the standard-library SQLite adapter behaved atomically under HoloDeck
process crashes. It does not prove storage-controller or filesystem behavior
under power removal, separate devices, independent operators, C2SP wire
compatibility, or production readiness. Active-record validation stays
`PENDING`; every operational authority remains false.

## Architecture

`SQLiteWitnessDurableStateStore` is a TruePanel-owned adapter behind the same
state-transition boundary as the prior file store. It uses:

- one SQLite database and one protected root directory per monitor;
- `journal_mode=WAL`, `synchronous=FULL`, and a bounded busy timeout;
- a store-identity table that prevents reuse for another monitor;
- `BEGIN IMMEDIATE` to serialize writers;
- a complete predecessor record digest in the transactional compare-and-swap;
- one canonical record containing successor state, transition digest, exact
  response signature, and predecessor digest;
- exact replay only when transition digest and signature both match;
- `PRAGMA integrity_check` before recovered state enters quorum evaluation;
- mode `0700` directories and mode `0600` database, WAL, and shared-memory
  files;
- an opt-in HoloDeck-only crash hook that is unreachable from a normal store.

The quorum adapter requires exactly two distinct monitor identities, two
distinct resolved database paths, healthy integrity checks, committed
signatures, and exact checkpoint and sequence agreement. It explicitly reports
zero independent production operators.

## Measurements

| Measure | Result |
| --- | ---: |
| Deterministic scenarios | 14 |
| PASS / expected HOLD | 7 / 7 |
| Isolated SQLite stores | 2 |
| Abrupt `SIGKILL` boundaries | 4/4 |
| Recovery Coverage Matrix | 12/12 trusted, 0 gaps |
| Precommit signature leaks | 0 |
| Postcommit signature losses | 0 |
| Rollback or concurrent-fork acceptances | 0 |
| Corrupt-store or split-checkpoint acceptances | 0 |
| Duplicate identity or path acceptances | 0 |
| Physical power-loss validations | 0 |
| Independent production operators | 0 |
| Shared-cooling first match | sample 19 |
| Isolated threshold first match | sample 46 |
| Correlation lead | 27 samples |
| Deployments / hardware actions / network calls | 0 / 0 / 0 |

The process-crash matrix kills a disposable child before transaction begin,
after begin, after the update but before commit, and after commit but before
response. The first three recover the predecessor with no signature. The last
recovers the successor and exact committed signature. This is stronger than a
raised exception because destructors and normal connection cleanup do not run.

## Prior-Art Field Report

Research and source inspection were refreshed on 2026-11-23.

| Candidate | What it supplies | Maturity, tests, fit, and weight | License / obligations | Recommendation |
| --- | --- | --- | --- | --- |
| [SQLite durability and testing](https://www.sqlite.org/testing.html) | WAL transactions, full synchronization, crash recovery, integrity checking, and dedicated VFS fault simulation. | Mature embedded engine already present through Python's standard library. Official tests simulate process, OS, I/O, and power failures. No service, container, credential, or network surface. | SQLite is public domain; Python distribution obligations are already part of TruePanel's runtime. | **Adopt the engine and its durability settings; keep TruePanel's record policy and quorum interface.** |
| [`transparency-dev/witness` SQLite store](https://github.com/transparency-dev/witness/blob/main/persistence/sqlite/sql.go) | WAL, `synchronous(FULL)`, busy timeout, serializable read-transform-write, transactional commit, and busy/locked pushback. | Actively maintained as of 2026-11-23. Its Go tests cover update semantics, configuration, latest state, and a prior deadlock. It is the closest production service fit, but brings Go service, HTTP, configuration, telemetry, and deployment surfaces. | Apache-2.0; preserve copyright, license, and notices if code is later reused. No source was copied. | **Best future production service candidate; do not embed it in this Python increment.** |
| [Jepsen](https://github.com/jepsen-io/jepsen) | Model-based histories, nemeses, and linearizability/consistency checking across real distributed nodes. | Active in November 2026 and exceptionally strong for multi-node verification. Clojure, remote-node orchestration, and a cluster harness are disproportionate for two local SQLite files. | Eclipse Public License; no code copied. | **Adapt the history-and-invariant idea when real remote witnesses exist.** |
| [Chaos Mesh](https://github.com/chaos-mesh/chaos-mesh) | Pod/process/network/block/IO fault injection with workflows and recovery. | Active in November 2026 with current fault-hardening work and broad Kubernetes test infrastructure. Requires Kubernetes controllers, CRDs, privileged daemons, and a much larger attack surface. | Apache-2.0; notices required if reused. | **Reject for the appliance-local checkride; reconsider only for a future Kubernetes witness deployment.** |
| [LitmusChaos](https://github.com/litmuschaos/litmus) | Chaos experiments, probes, results, workflows, and CI integration. | CNCF project with a 3.33.0 manifest in October 2026. Like Chaos Mesh, it adds a control plane, execution agents, CRDs, and Kubernetes operational weight. | Apache-2.0; notices required if reused. | **Reject for this increment; retain its explicit steady-state/probe/result model as inspiration.** |

### Build versus adopt

Adopt SQLite's existing transaction and recovery machinery through the Python
standard library. Build only the TruePanel-specific witness record, complete
predecessor comparison, identity isolation, quorum agreement, recovery coverage,
and negative-authority envelope. Do not build a new database engine, HTTP
witness service, or chaos control plane.

No third-party source, schema, package, binary, service, key, credential, or
network path was incorporated. The implementation was written against public
behavior and the repository's prior TruePanel interfaces. It can be replaced by
the maintained Go witness without changing Mission Control policy.

### Failed and rejected paths

- Reusing one SQLite path for two monitors was rejected: file separation is a
  minimum isolation property, even though it is not operator independence.
- Treating two database files on one temporary filesystem as two independent
  operators was rejected.
- Normal exception injection was rejected as the principal crash proof because
  it allows cleanup paths to run; the checkride uses abrupt child `SIGKILL`.
- Process death was not called power-loss validation. SQLite's official crash
  testing uses deeper VFS damage simulation; real target-device tests remain a
  production gate.
- `synchronous=NORMAL` was rejected because WAL commits can roll back after
  power loss; this adapter requires `FULL`.
- Chaos Mesh and Litmus were rejected because their Kubernetes control planes,
  privileges, and agents add more risk than they remove for this local test.
- Jepsen was not embedded because there is no distributed production witness
  topology to exercise yet.
- Automatic runtime promotion, repair, deployment, and hardware authority
  remain forbidden.

## Collaboration opportunity

The most useful external conversation remains with the
[`transparency-dev/witness`](https://github.com/transparency-dev/witness) and
[Armored Witness](https://github.com/transparency-dev/armored-witness)
maintainers. JT should ask for recommended deployment and recovery tests for two
separately governed witness instances, including key custody, WAL placement,
backup/restore invariants, and checkpoint-gossip failure handling. Jepsen's
maintainers become the strongest testing collaboration once two networked
operators exist.

## Reproduction

```bash
pytest -q tests/test_aegis_transparency_witness_sqlite_recovery.py
python -m truepanel.holodeck.aegis_transparency_witness_sqlite_recovery \
  --output /tmp/aegis-witness-sqlite-recovery.json
diff -u docs/evidence/aegis-transparency-witness-sqlite-recovery-checkride-v1.json \
  /tmp/aegis-witness-sqlite-recovery.json
node --check truepanel/web/static/reliability-view.js
python -m truepanel.hangar validate --root .
```

## Production gate

No deployment was performed. The next safe step is to place two governed
C2SP-compatible witnesses on separate physical devices, run controlled
power-cut recovery on the intended filesystems and storage controllers, and
compare recovered checkpoints and exact response signatures. Until that test
and operator governance exist, production trust remains false.
