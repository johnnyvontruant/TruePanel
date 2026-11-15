# AEGIS Intake-Bound Detector Result

## Outcome

The detector can no longer treat a recording path as proof that governed intake
occurred.  A new result envelope requires the exact canonical long-window intake
receipt, independently reconstructs it from the recording, then binds the receipt,
recording, detector contract, baseline, and replay result.  The earlier v1 result
remains historical evidence; it is not accepted as an intake receipt.

Success is limited to `INTAKE_BOUND_DETECTOR_RESULT_READY_FOR_CALIBRATION_BINDING`.
It is not field validation, candidate acceptance, installation, deployment, or
hardware authority.  The accepted Recovery Coverage Matrix remains 8/8 with zero
gaps.

## Architecture and safety boundary

1. The long-window gate snapshots one protected label-free recording and exports a
   canonical, public-only receipt.
2. The detector snapshots that protected receipt, rejects non-canonical bytes, and
   independently reconstructs the receipt from the recording.
3. Only an exact semantic and byte-for-byte match permits deterministic ORACLE and
   AEGIS replay.
4. The v2 result binds both lineage layers and keeps every production and operational
   authority false.

The exporter accepts no signer or private-key path. It creates new mode-0600 files
atomically and removes partial output after a failed write. It rejects symlinks,
unsafe permissions, receipt substitution, recording drift, labels, occupied outputs,
and the legacy v1 result schema.

## HoloDeck evidence

TP-EXP-0036 preserves ten deterministic paths: one exact receipt-bound replay and
nine HOLD outcomes. The positive fan-degradation scenario identifies shared cooling
at sample 19, versus isolated temperature threshold sample 46: 27 samples earlier.
No intake bypass, label, signer invocation, field validation, candidate acceptance,
installation, deployment, hardware action, or runtime write occurs.

Evidence: `docs/evidence/aegis-temperature-intake-bound-detector-result-v1.json`
(file SHA-256 `5ca7b28815834c3a8221fa7d3897a0e26560298f4bc74d2353fc8095062a888c`;
embedded evidence SHA-256 `fe1f9a1ef8e542e97218ecd1b665f319cc417ab5f7a1eb1e98060531d8bac58a`).

The first implementation compared parsed JSON only. An adversarial receipt with
appended whitespace therefore remained semantically equal. The final contract also
requires the exact canonical bytes and the scenario now holds closed.

## Prior-Art Field Report

| Candidate | What it supplies | Maturity / tests / fit | Dependency and security | License / attribution | Recommendation |
|---|---|---|---|---|---|
| [in-toto Statement v1](https://github.com/in-toto/attestation/blob/main/spec/v1/statement.md) | Immutable subjects identified by mandatory digests; clean statement/predicate/envelope separation | Stable specification with conformance-oriented repository; excellent conceptual fit for content-bound evidence | Zero runtime dependency when semantics are adapted; avoids trusting filenames | CC BY 4.0 specification; cite the project when adapting concepts | **Adapt the subject-digest and layer-separation ideas**, not its schema or code |
| [in-toto Link predicate](https://github.com/in-toto/attestation/blob/main/spec/predicates/link.md) | Explicit materials-as-inputs and subjects-as-products | Maintained specification; directly models receipt + recording → result lineage | No dependency needed; useful replaceable vocabulary | CC BY 4.0 specification | **Best architectural shortcut** for input/output lineage |
| [SLSA Provenance v1.2](https://slsa.dev/spec/v1.2/build-provenance) | `resolvedDependencies` for exact inputs and `subject` for outputs; downstream verification guidance | Current approved ecosystem standard with broad tooling; build-centric rather than telemetry-centric | Adopting the full stack would add disproportionate machinery; concepts are security-positive | Community Specification License 1.0 | **Adapt concepts only**; do not represent replay as a software build |
| [OpenLineage Version facet](https://openlineage.io/docs/spec/facets/dataset-facets/version_facet/) | Dataset versions and extensible lineage facets | Active 1.54 documentation, broad integrations, strong fit if TruePanel later exports fleet lineage | SDK/service is unnecessary for one local offline receipt; networked lineage would expand attack surface | Apache-2.0 implementation/specification repository | **Revisit for fleet-scale export**, not this local gate |

No external code, schema, package, service, credential, key, or dataset was copied or
added. TruePanel-owned interfaces implement the narrow behavior and tests make the
implementation replaceable. Full in-toto/SLSA envelopes were rejected because this
stage is unsigned replay lineage, not authenticated provenance; an envelope here
would suggest authority it does not possess. A live OpenLineage backend was rejected
because it adds network, retention, privacy, and availability obligations without
improving this deterministic local gate.

The most promising collaboration opportunity is the in-toto Attestation maintainers:
their subject/material model is the closest general-purpose vocabulary for the
receipt → replay result relationship. External contact remains out of scope.

## Reproduction

```text
pytest -q tests/test_aegis_temperature_intake_bound_detector_result.py tests/test_aegis_temperature_long_window_intake.py tests/test_aegis_temperature_detector_result_binding.py
python -c "from truepanel.holodeck.aegis_temperature_intake_bound_detector_result import run_temperature_intake_bound_detector_result_checkride as run; print(run()['measurements'])"
python -m truepanel.hangar validate --root .
node --check truepanel/web/static/reliability-view.js
```

## Next gate

Predeclare the statistical scoring contract—minimum sensitivity, specificity,
lead-time, uncertainty, and cohort size—before any authenticated outcome labels are
made available. A real protected long-window recording remains required before any
field claim; this increment does not authorize collection or deployment.
