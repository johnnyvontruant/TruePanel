# AEGIS anchored witness storage-fault corpus

## Outcome

This increment adds an immutable recovery anchor and a deterministic
storage-image fault corpus after the dual SQLite witness rehearsal. The anchor
binds the exact reviewed checkpoint, state sequence, per-monitor record digests,
and predecessor quorum result. Recovery is accepted only when both separately
rooted stores match every anchored value.

This closes an important rollback gap: two healthy databases agreeing with each
other is insufficient when both have been restored to the same stale image.
The anchor makes that matching rollback fail closed.

`ANCHORED_WITNESS_STORAGE_FAULT_RECOVERY_REHEARSED` remains a simulation
verdict. It does not claim an actual filesystem, storage controller, SSD/HDD,
UPS, kernel, or physical power cut was tested. Production trust and every
operational authority remain false.

## Architecture and measurements

`create_recovery_anchor()` accepts only the prior exact two-store quorum and
binds the checkpoint, sequence, each monitor's committed record digest, source
quorum digest, and negative authority claims. Recovery first runs SQLite
integrity, identity, signature, and peer-agreement checks, then requires every
value to match that external anchor.

The HoloDeck corpus checkpoints disposable databases and applies nine named
faults: zeroed header, truncation, record tamper, missing table, missing file,
joint stale rollback, split generation, swapped images, and cloned identity.
Two positive controls prove exact restart and exact image restore; anchor-tamper
and authority-escalation negatives complete the policy matrix.

| Measure | Result |
| --- | ---: |
| Deterministic scenarios | 13 |
| PASS / expected HOLD | 2 / 11 |
| Storage-image faults | 9 |
| Exact anchored recoveries | 2 |
| Recovery Coverage Matrix | 13/13 trusted, 0 gaps |
| Joint stale rollback acceptances | 0 |
| Split/corrupt/missing/substituted acceptances | 0 |
| Anchor-tamper acceptances | 0 |
| Physical power-loss validations | 0 |
| Independent production operators | 0 |
| Shared-cooling detection | sample 19 vs threshold 46; 27-sample lead |
| Deployments / hardware actions / network calls | 0 / 0 / 0 |

Evidence SHA-256:
`be23d6952ccc9c299f027c001f35fac5d7547a4eb331c0cbe19291cd4d3aae0f`.

## Prior-Art Field Report

Research and actual source inspection were refreshed on 2026-11-24.

| Candidate | What it supplies | Fit and maturity | License / provenance | Recommendation |
| --- | --- | --- | --- | --- |
| [SQLite testing](https://www.sqlite.org/testing.html) and [atomic commit](https://www.sqlite.org/atomiccommit.html) | Filesystem snapshots at successive I/O boundaries, characteristic unsynchronized-write damage, `integrity_check`, and the invariant that a transaction is wholly present or absent. | Mature embedded engine already used through Python. Its private TH3/TCL campaigns are much deeper than this application-layer corpus. | SQLite source is public domain. No source copied or modified. | **Adapt the snapshot/damage/invariant method; never claim equivalence to its VFS harness.** |
| [SQLite test VFS](https://github.com/sqlite/sqlite/blob/master/src/test_vfs.c) | Inspected source contains counted transient/persistent I/O faults and masks for open, sync, delete, write, truncate, read, locks, and shared memory. | Strongest low-level shortcut, but Python's standard binding cannot directly register this private harness; a custom SQLite build would enlarge the trusted base. | Source disclaims copyright; no code copied. | **Architectural reference; preserve a replaceable future VFS boundary.** |
| [FoundationDB Simulation](https://github.com/apple/foundationdb/blob/main/documentation/sphinx/source/testing.rst) | Deterministic seeds, controlled time, invariant workloads, replay, and aggressive component faults. | Mature and active, but inseparable from FoundationDB's C++ Flow runtime and too heavy for this adapter. | Apache-2.0; no code copied. | **Adopt deterministic inputs and invariants, not the framework.** |
| [Antithesis DST](https://antithesis.com/docs/resources/deterministic_simulation_testing/) | Seeded exploration, fault injection, property checks, and reproducible debugging. | Promising for a later containerized network-witness campaign; excessive for two local files. | Commercial service; nothing incorporated. | **Revisit after remote services exist.** |
| [Jepsen nemesis](https://github.com/jepsen-io/jepsen/blob/main/jepsen/src/jepsen/nemesis.clj) | Explicit setup/invoke/teardown fault operations and composable partitions. | Excellent for distributed histories; Clojure and multi-node orchestration are disproportionate now. | EPL; no code copied. | **Adapt the vocabulary later; do not embed.** |

### Build versus adopt

Adopt SQLite transactions and integrity checking. Build only the TruePanel-owned
content-addressed anchor, recovery policy, deterministic corpus, evidence
schema, and CI gate. No third-party source, package, binary, schema, service,
key, credential, or network path was incorporated.

### Rejected and failed paths

- Peer agreement without an external anchor was rejected because both stores
  can agree on the same rollback.
- Random unseeded byte fuzzing was rejected as irreproducible.
- Claiming WAL/FULL, `SIGKILL`, or image mutation as physical power-loss proof
  was rejected.
- Compiling SQLite's private test harness into the appliance was rejected for
  dependency and trusted-computing-base weight.
- FoundationDB, Antithesis, and Jepsen were rejected as direct dependencies at
  this stage.
- Guessing or synthesizing damaged state was rejected; AEGIS holds instead.

## Collaboration and production gate

The best immediate collaboration is with
[`transparency-dev/witness`](https://github.com/transparency-dev/witness),
[Armored Witness](https://github.com/transparency-dev/armored-witness), and
SQLite testing experts: establish where the anchor should be independently
published and the smallest supported public VFS shim for application-specific
crash campaigns.

No deployment was performed. The next gate remains two separately governed
physical witnesses on separate devices, with the anchor held outside both
stores and a recorded controlled physical power cut on the intended filesystem
and controller stack. Until then, production trust is false.

## Reproduction

```bash
pytest -q tests/test_aegis_transparency_witness_storage_faults.py
python -m truepanel.holodeck.aegis_transparency_witness_storage_faults \
  --output /tmp/aegis-witness-storage-faults.json
diff -u docs/evidence/aegis-transparency-witness-storage-faults-checkride-v1.json \
  /tmp/aegis-witness-storage-faults.json
```
