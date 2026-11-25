# AEGIS governed long-window intake

## Outcome

This increment creates a separate, read-only Black Box boundary for correlation
calibration. It does not reuse the four-frame recovery ceremony. One protected
JSONL snapshot may reach
`LONG_WINDOW_RECORDING_ACCEPTED_FOR_LABEL_BLIND_REPLAY` only after byte, frame,
ordering, privacy, required-signal, stable-baseline, and label-exclusion checks.

The intake never captures, tails, checkpoints, rewrites, deletes, or repairs a
source. Success is permission to perform a later label-blind replay, not a
detector result, validation, acceptance, installation, deployment, or hardware
action.

## Architecture

1. Open one absolute canonical operator-owned regular file with no symlink
   traversal and no group/world write permission.
2. Bound the snapshot to 16 MiB, 10,000 frames, and the existing 256 KiB
   Black Box per-frame limit; compare descriptor and path identity before and
   after the single read.
3. Reconstruct every frame through `BlackBoxFrame`, require canonical sanitized
   data, contiguous sequence numbers, and strictly increasing capture times.
4. Require fan PWM/RPM plus drive/CPU temperature in every frame.
5. Require at least 24 frames and a stable 12-frame baseline; reject outcome or
   ground-truth label keys anywhere in the recording.
6. Preserve a content digest and explicit zero-authority fields. The file path
   is never retained.

The packaged fan-bearing recording supplies 52 frames. Its first 12 frames meet
the predeclared baseline ranges. This gate deliberately does not run the
detector or inspect the later outcome.

## Prior-art field report

Research was refreshed on 2026-10-20 against the projects' current
documentation and implementation surfaces.

| Candidate | Useful capability | Maturity, fit, and dependency weight | License / obligations | Build versus adopt |
|---|---|---|---|---|
| [OpenTelemetry filelog receiver](https://github.com/open-telemetry/opentelemetry-collector-contrib/blob/main/receiver/filelogreceiver/README.md) | Bounded log entries, file fingerprints, offset persistence, rotation/truncation handling, operator pipeline | Active CNCF ecosystem with substantial tests; its service, polling, offsets, and mutation-capable feature gates exceed a one-shot offline intake | Apache-2.0; preserve license/notice if code is copied | **Adapt limits and identity thinking only.** TruePanel uses an exact whole-file SHA-256 plus stable descriptor/path identity. No code or package adopted. |
| [Fluent Bit Tail input](https://docs.fluentbit.io/manual/4.2/data-pipeline/inputs/tail) and [implementation](https://github.com/fluent/fluent-bit/blob/master/plugins/in_tail/tail.c) | Inode/filename tracking, SQLite checkpoints, rotation and `copytruncate` handling | Mature, active, well-tested collector; excellent for continuous shipping, but checkpoints and a running watcher violate this ceremony's zero-write, one-shot boundary | Apache-2.0 | **Reject runtime adoption.** The explicit `tailing_performed=false` and `checkpoint_write_performed=false` contract prevents accidental drift toward a daemon. |
| [Prometheus TSDB storage](https://prometheus.io/docs/prometheus/latest/storage/) | Ordered time-series blocks, bounded retention, WAL replay, snapshots | Very mature and heavily tested; appropriate if TruePanel later needs durable fleet-scale telemetry, disproportionate for a signed local artifact | Apache-2.0 | **Adapt bounded-window semantics only.** Do not add a TSDB or WAL until real retention/query requirements exist. |
| [OpenLineage dataset version facet](https://openlineage.io/docs/spec/facets/dataset-facets/version_facet/) and [lineage facet](https://openlineage.io/docs/spec/facets/dataset-facets/lineage/) | Exact dataset versions and input/output derivation | Active Linux Foundation project with multi-language implementations; strong interoperability path, but an event backend is unnecessary here | Apache-2.0 | **Keep the interface replaceable.** A future export can map the recording digest and later detector result to facets without changing intake trust. OpenLineage maintainers are the strongest collaboration opportunity. |

No external code, schema, binary, package, service, credential, key, or dataset
was incorporated. The implementation is standard-library Python behind a
TruePanel-owned interface, so there is no new attribution or runtime obligation.

## Rejected and failed paths

- **Reuse the four-frame recovery intake:** rejected because it proves one
  recovery transition, not a correlation baseline and drift window.
- **Accept frame count alone:** failed review because reordered, label-bearing,
  missing-signal, or already-drifting baselines can still have enough frames.
- **Tail the live Black Box:** rejected because a watcher introduces mutable
  offsets, rotation races, long-running access, and a production-service
  boundary.
- **Use OpenTelemetry, Fluent Bit, or Prometheus now:** rejected because their
  continuous ingestion and persistence strengths are unnecessary dependency
  and security surface for one bounded offline artifact.
- **Infer a detector outcome during intake:** rejected because intake must stay
  label-blind and policy-neutral. Detection remains a later, separately bound
  action.

## HoloDeck evidence and open risks

TP-EXP-0035 preserves ten deterministic scenarios: one accepted 52-frame
window with a 12-frame baseline and nine HOLD outcomes. HOLD covers short input,
symlink substitution, unsafe permissions, malformed JSON, label leakage,
missing signals, sequence/time reordering, and unstable baseline. Accepted
labels, capture/tail/checkpoint operations, validation, candidate acceptance or
installation, deployment, hardware actions, and runtime writes are all zero.

The ranges prove only that the opening fixture segment is internally stable;
they are not field-calibrated physiological limits for every chassis or
workload. The next gate must bind this intake record into detector-result
creation and then predeclare statistical sensitivity, specificity, lead-time,
and uncertainty criteria before comparing predictions with authenticated
labels.
