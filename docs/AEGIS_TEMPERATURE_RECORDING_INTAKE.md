# AEGIS protected temperature recording intake

Reviewed 2026-10-14. This increment closes the file-to-checkride boundary left
open by PR #208. It accepts one operator-provided, privacy-sanitized Black Box
JSONL artifact; it does not capture, tail, poll, delete, rewrite, or repair the
source.

## Architecture and authority

`evaluate_temperature_recording_intake` opens an absolute canonical path with
`O_NOFOLLOW`, requires a current-operator-owned regular file that is not group-
or world-writable, bounds the complete artifact to four Black Box frame limits,
and compares device, inode, mode, owner, size, mtime, and ctime before and after
the read. It then requires exactly four nonblank UTF-8 JSON objects and delegates
all authentication, privacy, ordering, identity, fault, and recovery decisions
to PR #208's existing checkride.

The returned evidence contains the byte digest and count, never the source path.
Even successful field-shaped evidence is only eligible for a separate
calibration review. It cannot validate production, accept or install the 9/9
candidate, write runtime state, deploy, or control hardware.

## HoloDeck evidence

TP-EXP-0029 preserves twelve deterministic scenarios: one protected simulation
passes, one reviewed opt-in field-shaped fixture reaches separate review, and
ten adversarial cases HOLD. The holds cover an invalid SSHSIG, raw identity,
unsafe permissions, symlink substitution, malformed JSON, an extra frame,
incomplete recovery, member drift, an ungoverned source, and missing outcome
review.

Evidence: [`aegis-temperature-recording-intake-v1.json`](evidence/aegis-temperature-recording-intake-v1.json),
self-digest `100e5ba4fabdc75d12b24ca1df49095c9ac7ed875374a87b095f128f708cc15c`.

## Prior-Art Field Report

The strongest candidates were inspected in their current documentation and
implementation, not only by project description.

| Candidate | What the code/docs supply | Maturity, tests, maintenance | Platform/dependency/security fit | License and attribution | Decision / verified time saved |
|---|---|---|---|---|---|
| [OpenTelemetry Collector filelog receiver](https://github.com/open-telemetry/opentelemetry-collector-contrib/tree/main/receiver/filelogreceiver) and [file consumer](https://github.com/open-telemetry/opentelemetry-collector-contrib/blob/main/pkg/stanza/fileconsumer/file.go) | Fingerprints, checkpoints, bounded batches, file tracking, polling, and explicit unreadable-file limits. The inspected implementation starts a polling goroutine and persists offsets. | Active, beta log receiver with named code owners, published coverage, and the Collector's broad test infrastructure. | Excellent reference for identity and boundedness; poor direct fit for a four-frame offline ceremony because it introduces a large Go service and continuous watcher/state machinery. | Apache-2.0; preserve copyright, license, and NOTICE if code is redistributed. | **Adapt ideas only.** It validated inode/content identity as a real concern, saving a custom watcher experiment; no code copied. |
| [Fluent Bit Tail](https://docs.fluentbit.io/manual/4.2/data-pipeline/inputs/tail) and [tail file implementation](https://github.com/fluent/fluent-bit/blob/master/plugins/in_tail/tail_file.c) | Per-file buffers, maximum record sizes, inode/filename offset state, offset markers, EOF batch mode, symlink/stat handling, and at-least-once resumption. | Long-lived active project with a native test matrix and production deployments. The inspected 2026 source computes an offset marker around the saved position. | Capable but far heavier than required; adds a native daemon, SQLite/checkpoint writes, globbing, watcher semantics, and a larger attack/configuration surface. | Apache-2.0 with notice obligations if incorporated. | **Reject dependency; adapt bounded-record principle.** A one-shot standard-library reader avoids service and database work. |
| [in-toto Statement v1](https://github.com/in-toto/attestation/blob/main/spec/v1/statement.md) | Immutable subject identity by digest and a typed predicate boundary. | Small, stable specification maintained by the in-toto community; schema-oriented tests rather than a file reader. | Strong conceptual fit for binding the imported bytes without retaining their location; adding its runtime is unnecessary because TruePanel already uses content digests and SSHSIG. | Apache-2.0. Attribution required only if material is redistributed. | **Adapt semantics.** The result records SHA-256 and byte count as the subject boundary; no schema or code copied. |
| [smartmontools JSON output](https://www.smartmontools.org/static/doxygen/smartctl_8cpp_source.html) | Mature drive telemetry serialization and explicit JSON output used by NAS ecosystems. | Mature and actively maintained, with hardware-specific breadth that TruePanel should not reimplement. | Remains the preferred upstream producer concept, but this intake must consume only an already-sanitized TruePanel Black Box artifact and never invoke drives. | GPL-2.0-or-later project; linking/copying would require careful compatibility review. | **Interoperate, do not copy.** No smartmontools code, process invocation, or hardware access was added. |

### Build-versus-adopt conclusion

The mature log agents solve a different problem: continuous multi-file
collection with offsets, watchers, rotation, and checkpoint state. Adopting one
would add code, processes, configuration, and writes while weakening the
ceremony's exact-file semantics. The smallest legitimate shortcut is a
TruePanel-owned standard-library adapter that adopts their bounded-read and
stable-identity lessons, delegates domain decisions to the existing checkride,
and can later be replaced behind the same function.

No third-party code, dependency, schema, binary, service, credential, key, or
dataset was incorporated. The implementation uses Python and POSIX interfaces
already required by TruePanel. The OpenTelemetry filelog/fileconsumer
maintainers are the most promising collaboration opportunity: their experience
with file identity, truncation, fingerprint collisions, and checkpoint
boundaries could sharpen a future portable snapshot abstraction.

## Failed and rejected paths

- A general-purpose tailer was rejected because polling and checkpoint writes
  are authority expansion, not a shortcut for an immutable four-frame handoff.
- Reading with `Path.read_text()` was rejected because it cannot express
  no-follow open semantics or prove the opened inode stayed bound to the path.
- Silently sanitizing raw identifiers during import was rejected; changed
  content means the operator did not review the admitted artifact.
- Returning the recording path was rejected because filesystem locations may
  expose operator identity or host layout and are unnecessary after hashing.
- Treating a valid recording as field validation was rejected. Fixture success
  proves only the admission and replay machinery.

## Open risks and next gate

The current protected reader depends on POSIX ownership and `O_NOFOLLOW`; a
future Windows implementation needs an equivalent owned-handle/reparse-point
contract. A real JT public roster, detached development-only signature, and
separately authorized sanitized recording still do not exist. The next gate is
operator-controlled key enrollment and offline signing, followed by this
read-only intake against one reviewed recording. Production installation and
deployment remain separate decisions.
