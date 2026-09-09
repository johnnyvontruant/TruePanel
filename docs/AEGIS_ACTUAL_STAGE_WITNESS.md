# AEGIS actual-stage witness

Project MANUAL PROMOTION GATE originally accepted a caller-supplied stage digest. Project ACTUAL STAGE WITNESS closes that gap by deriving the promotion request from the staged filesystem itself.

## Contract

- The stage root and manifest must be absolute, real directories/files rather than symlinks.
- The manifest must remain validated, unpromoted, service-clean, bounded in size, and bound to the exact stage root.
- Every promoted regular file is opened without following symlinks, hashed, and checked with descriptor metadata before and after reading.
- Directory metadata is checked before and after traversal so concurrent additions, removals, or replacements fail closed.
- Symlinks, special files, oversized files, oversized trees, excessive entry counts, version mismatch, or post-review content drift produce `HOLD`.
- The tree digest covers exactly the deployable payload. Preserved configuration, runtime environments, generated caches, the manifest, receipts, and the managed CLI wrapper remain outside that digest in agreement with guarded-promotion exclusions.
- Success means only `READY_FOR_EXTERNAL_REVIEW`. It creates no signature, receipt, file, promotion, service change, or control authority.

## HoloDeck proof

The deterministic rehearsal builds disposable staged filesystems and removes them at completion. One actual validated stage reaches external review. Payload symlink, already-promoted state, manifest/root mismatch, candidate-version mismatch, and post-review payload tamper all hold. False readiness, production-stage writes, review signatures, promotion executions, service changes, production mutation, and control authority remain zero.

## Prior art and build-versus-adopt

- TUF target hashes and consistent snapshots reinforce binding review to immutable bytes and metadata.
- Python's `lstat`, descriptor `fstat`, and `O_NOFOLLOW` primitives provide the small local mechanism needed to reject link substitution and detect changes during the scan.
- A general artifact-signing or software-update framework remains unnecessary at this layer: the witness creates evidence but neither authenticates reviewers nor distributes artifacts.

The implementation is original and dependency-free. No external source, schema, binary, service, credential, or notice-bearing artifact was incorporated.

## Rejected paths

- Trusting a digest supplied beside the manifest: it does not prove which bytes were inspected.
- Hashing the manifest only: it contains no complete deployable-file inventory.
- Following symlinks: a reviewed path could resolve outside the stage.
- Hashing preserved `truepanel.yaml` or `.venv`: those bytes are not promoted and would create misleading review churn.
- Writing the witness into the stage: that mutates the subject being reviewed and creates a circular digest.

## Reproduction

Run `pytest -q tests/test_aegis_stage_witness.py tests/test_aegis_promotion_gate.py`, replay `run_stage_witness_checkride()`, validate HANGAR, and run the installed-wheel smoke outside the checkout.

The strongest next step is a replaceable operator-owned public-signature verifier for the witnessed request, followed by a sandboxed end-to-end rehearsal that stops before the confirmation phrase and any service change.
