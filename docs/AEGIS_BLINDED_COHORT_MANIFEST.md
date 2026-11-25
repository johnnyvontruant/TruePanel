# AEGIS Two-Phase Blinded Cohort Manifest

## Outcome

AEGIS now freezes the complete eligible intake inventory before detector predictions
or authenticated outcomes are visible, then requires exactly one independently
digest-verified label-blind result for every planned case. The canonical manifest is
content-addressed and independent of caller list order. Missing, extra, duplicate,
drifted, relabeled, or post-freeze-edited members fail closed.

The successful state is only `BLINDED_COHORT_MANIFEST_FROZEN`, ready for a future
authenticated label join. It does not accept labels or scores and grants no field
validation, candidate acceptance, installation, runtime, deployment, storage,
network, or hardware authority. The accepted Recovery Coverage Matrix remains 8/8
trusted with zero gaps.

## Two-phase contract

1. Validate the exact predeclared statistical contract from PR #217.
2. Freeze at least 440 unique opaque case identities, recording digests, governed
   intake digests, receipt digests, and non-outcome strata before predictions exist.
3. Require at least two system profiles and four workload classes without using
   incident outcomes.
4. Join exactly one intake-bound detector result to every planned case.
5. Independently recompute every result digest and require one detector contract.
6. Canonically sort by opaque case ID so input ordering cannot alter cohort identity.
7. Preserve compact result descriptors without labels; expose only readiness for a
   separately authenticated label join.

This invalidates a weak assumption in the original roadmap: freezing results alone
does not prevent selection bias. A producer could inspect predictions and omit
unfavorable recordings before creating the manifest. Freezing the intake inventory
first makes later completeness mechanically testable.

## HoloDeck evidence

TP-EXP-0038 preserves 12 deterministic paths: two equivalent frozen manifests and
ten HOLD outcomes. The successful paths contain 440 planned intakes and 440 results
across two system profiles and four workloads; reversing input order produces the
same manifest identity.

HOLD covers a missing planned result, an unplanned result, a duplicate result,
result-digest tampering, recording substitution, detector-contract drift, prediction
leakage into the plan, outcome-label injection, statistical-contract substitution,
and post-freeze authority editing.

Evidence: `docs/evidence/aegis-temperature-blinded-cohort-manifest-v1.json`
(file SHA-256 `d3b0f561d09edb87f3f00b1b55fce8fac32c98d446743bee9f1188aeefdf10c7`;
embedded evidence SHA-256
`82912a4b8bb0f14438c184595cba576ad6f115ecc5320752b6dad98637467a03`).

Accepted omissions, unplanned results, duplicate results, labels, scores, field
validations, candidate acceptances, installations, deployments, hardware actions,
and runtime writes are all zero.

## Prior-Art Field Report

| Candidate | Capability and lesson | Maturity / test quality | Platform and dependency fit | License / attribution | Recommendation |
|---|---|---|---|---|---|
| [MLCommons Croissant](https://github.com/mlcommons/croissant/blob/main/docs/croissant-spec.md) | FileObject SHA-256 values bind declared dataset resources to downloaded content | Active specification, extensive examples and validator implementation | Rich JSON-LD metadata is valuable for interchange but disproportionate for one internal manifest | Code/examples Apache-2.0; specification has separate CC BY-ND terms—retain notices if adopted | **Adapt checksummed-resource semantics only** |
| [in-toto Attestation Statement v1](https://github.com/in-toto/attestation/blob/main/spec/v1/statement.md) | Subjects bind names to immutable digest sets; implementation validation requires subjects and digests | Mature supply-chain standard with schemas, language implementations and tests | Excellent semantic model, but importing its verifier does not solve cohort-selection completeness | Apache-2.0; preserve license and attribution if code or schemas are incorporated | **Adapt subject/digest semantics behind TruePanel’s interface** |
| [OpenLineage](https://openlineage.io/docs/spec/object-model/) | Dataset-version and lineage facets distinguish one immutable dataset state and its inputs | Active standard, multiple clients, compatibility tests and production integrations | Strong future interchange option; client stack and event transport add no value to this offline gate | Apache-2.0; preserve license and notices if later adopted | **Revisit for fleet-scale lineage export** |
| [DVC](https://dvc.org/doc/user-guide/project-structure/internal-files) | Content-addressed cache separates logical names from immutable data identity and deduplicates identical content | Mature project with broad automated tests and multiple storage backends | Full CLI, cache, remote and telemetry dependency graph is much heavier than a deterministic manifest | Apache-2.0; preserve license and notices if adopted | **Adapt content identity; do not add DVC now** |

No external code, schema, package, binary, service, credential, key, or dataset was
added. TruePanel uses its own canonical JSON, SHA-256, strict-schema, and fail-closed
interfaces. Croissant JSON-LD was rejected because interoperability is not yet worth
its schema and licensing complexity. DVC was rejected because cache and remote-data
management are outside this gate. OpenLineage event transport was rejected because
the manifest is offline and immutable. The in-toto verifier was not added because
digest binding alone cannot prove that the inventory was complete before prediction.

OpenLineage is the strongest collaboration opportunity once TruePanel needs to export
lineage across several NAS systems or independent scorers. Croissant maintainers are
also worth approaching if AEGIS calibration corpora become publishable datasets.
External contact remains out of scope.

## Failed assumptions and open risks

- Freezing detector results alone does not prevent prediction-aware case selection.
- Caller list order must not define cohort identity.
- A stored result digest must be independently recomputed before admission.
- A 440-case total does not guarantee the future 40-positive/400-negative outcome
  balance; that can only be assessed after authenticated labels are joined.
- The HoloDeck 440-case fixture proves contract behavior, not field accuracy.
- No real JT signature, governed intake inventory, field recording, or outcome label
  has entered this path.
- The pure manifest builder is intentionally storage-neutral; a future persistent
  implementation needs the existing protected, atomic POSIX publication boundary or
  an equivalent replaceable store.

## Next gate

Define a one-shot authenticated label-join receipt that verifies this exact frozen
manifest, accounts for every member, and evaluates the PR #217 contract once. It must
not allow exclusions, threshold changes, repeated scoring attempts, validation claims,
promotion, deployment, or hardware authority.
