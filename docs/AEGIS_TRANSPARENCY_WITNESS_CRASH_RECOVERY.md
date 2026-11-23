# AEGIS transparency witness crash recovery

## Outcome

This follow-up closes the simulated durability gap after witness-state
continuity. A verified transition, its exact response signature, and the
successor checkpoint state are stored as one content-addressed record. The
adapter flushes the temporary record, atomically replaces the committed
record, and flushes the containing directory before returning the signature.

An exclusive file lock serializes compare-and-swap updates. After a crash:

- an unrenamed temporary record is discarded and cannot release a signature;
- a visible committed successor retains the exact signature for idempotent
  replay;
- a competing transition from the same predecessor is rejected;
- corruption, symlinks, identity drift, checkpoint substitution, missing
  signatures, and authority escalation fail closed.

The adapter writes only to temporary HoloDeck directories in this checkride.
It is not enabled by the runtime and does not claim that a particular NAS
filesystem, disk cache, controller, or power-loss path has been validated.

## Architecture

`WitnessDurableStateStore` is a TruePanel-owned boundary around five explicit
operations: initialize, read, compare, commit, and recover. Callers provide an
already verified continuity result and exact signed transition. The adapter
does not fetch checkpoints, contact witnesses, hold production keys, or grant
network, storage, runtime, deployment, or hardware authority.

The commit boundary is:

1. acquire an exclusive lock;
2. re-read and authenticate the current content-addressed record;
3. compare the complete six-field predecessor identity;
4. place successor state, transition digest, and response signature in one
   record;
5. write with mode `0600`, flush, and `fsync` the temporary file;
6. replace the committed path atomically;
7. `fsync` the parent directory;
8. only then return the stored signature.

This is intentionally a replaceable file adapter. A production service can
implement the same compare-and-swap and replay contract with SQLite or a
separately operated C2SP witness without changing AEGIS policy.

## HoloDeck checkride

The deterministic checkride covers fourteen paths:

- clean durable commit;
- exact idempotent replay;
- crashes before write, after temporary-file flush, after replacement, and
  after directory flush;
- serialized concurrent fork and stale compare-and-swap rejection;
- corrupt record rejection;
- authority escalation, unverified monitor, missing recoverable signature,
  checkpoint substitution, and pending-file symlink holds.

Result: nine recovery/contract paths pass and five adversarial inputs hold.
Across four crash points there are zero precommit signature leaks, postcommit
signature losses, rollback acceptances, concurrent-fork acceptances, corrupt
state acceptances, or authority escalations. Recovery Coverage Matrix progress
is 11/11 trusted with zero gaps. Shared-cooling correlation remains sample 19
versus isolated threshold sample 46, a 27-sample lead.

## Prior-art field report

| Candidate | Actual material inspected | Capability, fit, maturity, and security | License / obligations | Decision |
| --- | --- | --- | --- | --- |
| [C2SP tlog-witness v1.0.0](https://c2sp.org/tlog-witness@v1.0.0) | Current `add-checkpoint` transaction and persistence requirements. | Normatively requires persistence before response and makes the stale-check/commit race explicit. Exact policy fit, no implementation dependency. | Open specification; no source copied. | **Adopt the contract.** The signature is unavailable until durable state succeeds. |
| [transparency-dev/witness](https://github.com/transparency-dev/witness) | `persistence/sqlite/sql.go` at `bd0f4ab`: WAL mode, one-second busy timeout, `synchronous(FULL)`, serializable transaction, read-transform-write callback, commit, and busy/locked pushback; `witness/witness.go`; tests; `go.mod`; LICENSE. | Strongest maintained implementation. Its SQLite transaction is a legitimate production shortcut and handles concurrency better than inventing a network service. Embedding its Go service now would add deployment, key, HTTP, database, telemetry, and operator surfaces. | Apache-2.0. No code, schema, binary, or Go dependency copied. | **Production-service candidate.** Preserve the TruePanel interface and evaluate a separately operated instance later. |
| [SQLite atomic commit](https://www.sqlite.org/atomiccommit.html) | Official rollback-journal, locking, flush, recovery, and directory-sync description. | Exceptionally mature crash-recovery engine. Python already ships an SQLite binding, but internal fault stages are less transparent to this small deterministic checkride and would move testing below the policy boundary. | Public SQLite documentation; SQLite code is public domain. No source copied. | **Prefer for production-backed state after device testing.** Keep this file adapter as the inspectable HoloDeck model. |
| [Linux `fsync(2)`](https://man7.org/linux/man-pages/man2/fsync.2.html) | Current manual semantics for data/metadata flush and the separate directory-entry durability requirement. | Directly supplies the minimum primitives for one small record. Behavior still depends on filesystem, kernel, device, controller, and truthful flush implementation. | Linux man-pages are GPL-2.0+ with project-specific exceptions; documentation facts only, no text/source copied. | **Use through Python standard library for simulation.** Require real device-backed power-cut testing before production. |
| [Armored Witness](https://github.com/transparency-dev/armored-witness/blob/main/docs/transparency.md) | Dedicated witness state/key isolation and append-only verification architecture. | Best operator-isolation model, but requires hardware, firmware trust, provisioning, recovery ceremonies, and external operation. | Apache-2.0. No firmware or source incorporated. | **Best collaboration target** for two independently governed witness operators. |
| [Sigsum](https://github.com/sigsum/sigsum-go) | Witness cosignature and verifier-policy architecture. | Strong independent implementation reference. Adopting the full ecosystem does not improve this local durability contract. | BSD-2-Clause. No code copied. | **Retain for independent interoperability comparison.** |

### Build versus adopt

Build only the small replaceable policy adapter and deterministic fault model.
For production, adopt the maintained C2SP witness service or an SQLite-backed
implementation rather than expanding the file adapter into a general witness
daemon. The current adapter saves verified development time by using Python's
standard `flock`, `fsync`, and `replace` primitives and by reusing the existing
continuity verifier; it adds no package or service.

### Rejected and failed paths

- Treating `rename` alone as durable was rejected: directory metadata needs an
  explicit flush at this trust boundary.
- Recreating a signature after restart was rejected: recovery may release only
  the exact signature stored in the committed record.
- Promoting an unrenamed temporary file was rejected: the committed pathname
  is the sole authority; abandoned temp state is discarded.
- Last-writer-wins updates were rejected: a complete predecessor identity is
  compared under one exclusive lock.
- Calling temporary-filesystem tests power-loss proof was rejected. The
  checkride verifies ordering and recovery logic, not physical durability.
- Embedding the complete Go witness or adding a production SQLite database was
  deferred because there are still zero independent production operators and
  no approved external log entry.

## Provenance

No third-party code, binary, schema, package, fixture, key, credential, service,
or runtime dependency was added. The implementation is original TruePanel code
behind a replaceable interface. The C2SP rule, transparency-dev transaction,
SQLite recovery model, and Linux durability primitives are attributed above.
Existing project licensing and notice obligations are unchanged.

## Reproduction

```console
pytest -q tests/test_aegis_transparency_witness_crash_recovery.py
python -m truepanel.holodeck.aegis_transparency_witness_crash_recovery \
  --output /tmp/aegis-witness-crash-recovery.json
diff -u docs/evidence/aegis-transparency-witness-crash-recovery-checkride-v1.json \
  /tmp/aegis-witness-crash-recovery.json
python -m truepanel.hangar validate --root .
node --check truepanel/web/static/reliability-view.js
```

## Remaining gate

Commission two separately operated witnesses over one privacy-safe external
log entry, place each state store on its intended production filesystem and
storage path, and perform controlled device-backed power-cut testing. Compare
both recovered checkpoints and replayed signatures before any active record is
called production trusted. No live-host or hardware test is authorized by this
increment.
