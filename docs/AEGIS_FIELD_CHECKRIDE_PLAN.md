# AEGIS Field-Checkride Plan and Prior-Art Field Report

## Outcome

This increment creates a content-addressed, passive-only field-checkride test card from one authenticated `APPROVE_FOR_MANUAL_FIELD_CHECKRIDE_PLANNING` appraisal. It independently reverifies the appraisal statement, OpenSSH SSHSIG, immutable receipt, exact candidate dossier, all seven dossier subjects, and the accepted 8/8 Recovery Coverage Matrix before writing the plan.

Success reaches only `READY_FOR_SEPARATE_FIELD_CHECKRIDE_CONFIRMATION`. The packet contains seven exact passive observations, six abort criteria, seven required evidence items, privacy limits, preflight conditions, and success criteria. It cannot access BattleStation, start capture, consume a recording, validate or accept a candidate, install or deploy software, mutate storage or networking, or actuate hardware. A separately designed confirmation remains mandatory.

## Deterministic proof

TP-EXP-0044 rehearses ten paths: one exact plan is ready for separate confirmation and nine paths HOLD. HOLD covers an operator appraisal HOLD, appraisal receipt substitution, live-host source permission, privacy relaxation, a removed abort condition, automatic capture, hardware-authority escalation, an unknown contract field, and occupied output.

The accepted test card preserves the existing shared-cooling target: AEGIS first matches at sample 19, the first isolated threshold occurs at sample 46, and the lead is 27 samples. The rehearsal performs zero confirmations, recording reads, captures, BattleStation accesses, field-checkride authorizations, validations, acceptances, installations, deployments, hardware actions, or runtime writes.

## Exact observation and safety contract

The plan requires fan speed, fan speed ratio, CPU temperature, system temperature, physical-disk temperature, monotonic sequence, and UTC timestamp. It accepts only an operator-supplied, sanitized, content-addressed Black Box recording after separate confirmation. Hostnames, network addresses, credentials, disk identifiers, pool contents, and paths are forbidden.

The test card aborts on evidence identity or custody drift; missing, stale, non-finite, or discontinuous signals; any hard thermal or fan alert; baseline, workload, profile, or sensor drift; privacy leakage; or any request for live-host, capture, configuration, service, storage, network, or hardware authority. Aborted plans cannot be resumed or silently weakened.

## Prior-art comparison

Research was refreshed on 2026-10-28 and included the actual documentation and source linked below.

| Candidate | What the code or documentation supplies | Maturity and maintenance | Platform fit / dependency weight | Security and license | Recommendation |
| --- | --- | --- | --- | --- | --- |
| [NASA Test Readiness Review](https://nodis3.gsfc.nasa.gov/displayCA.cfm?Internal_ID=N_PR_7123_001C_&page_name=AppendixG) and [NASA flight test-card practice](https://ntrs.nasa.gov/citations/20230003007) | Defined objectives, configuration control, test procedures, data handling, success criteria, contingency plans, and review of every abort response before execution. | Institutional, safety-oriented process; not a software dependency. | Excellent conceptual fit for separating plan readiness from execution readiness. | U.S. government material; concepts only, with source attribution. | **Adapt the test-card and readiness-review semantics.** |
| [AWS Fault Injection Service stop conditions](https://docs.aws.amazon.com/fis/latest/userguide/stop-conditions.html) | Named steady state, threshold-based stop conditions, terminal stop behavior, and no resume after a stop. | Commercially operated and documented. | Strong guardrail idea but AWS/CloudWatch specific and unsuitable as a NAS dependency. | Proprietary service and documentation; no code copied. | **Adapt terminal stop semantics only.** |
| [LitmusChaos probes](https://github.com/litmuschaos/litmus-go/blob/fd7e7a5c5f2b96e769e140ef6aa4d23367186f98/pkg/probe/probe.go) | Actual Go implementation runs pre-, during-, and post-chaos probes; `StopOnFailure` marks the probe stopped and returns the error rather than continuing. | Active, test-bearing cloud-native project; repository activity was current during this review. | Kubernetes-oriented and dependency-heavy for TruePanel, but its phase/probe model transfers cleanly. | Apache-2.0; copying would require notice preservation. No code copied. | **Adapt fail-closed probe phases, do not adopt the runtime.** |
| [Chaos Mesh workflow API](https://github.com/chaos-mesh/chaos-mesh/blob/master/api/v1alpha1/workflow_types.go) | The source exposes per-template deadlines, status checks, and `AbortWithStatusCheck`, with typed workflow conditions. | Active CNCF-style project with extensive controller and end-to-end coverage. | Kubernetes controllers and CRDs are far too heavy for an offline NAS test card. | Apache-2.0; no code or schema copied. | **Architectural inspiration only.** |
| [OpenTelemetry hardware semantic conventions](https://github.com/open-telemetry/semantic-conventions/tree/main/model/hardware) | Source YAML defines `hw.fan.speed` in rpm, `hw.fan.speed_ratio`, `hw.temperature` in Celsius, sensor location, limits, and explicit fan/temperature states. | Maintained, generated, cross-vendor conventions; hardware conventions remain development status. | Best naming shortcut and future interoperability path. No collector or SDK is required for this plan. | Apache-2.0; names and concepts adapted, no generated bindings or source copied. | **Adapt metric names behind a TruePanel-owned contract; revisit when conventions stabilize.** |
| [NASA cFE functional-test states](https://github.com/nasa/cFE/blob/dev/docs/README_functionaltest.md) | Actual test framework distinguishes an assertion failure from a sequence `ABORT` where a major failure makes continuation unsafe. | Long-lived flight-software project with functional-test infrastructure. | Useful vocabulary but adopting cFS/cFE would be disproportionate. | Apache-2.0; semantics only. | **Retain explicit terminal ABORT evidence.** |

## Build versus adopt

TruePanel should own the compact JSON plan and verifier because its trust boundary joins AEGIS-specific appraisal, dossier, Recovery Coverage Matrix, HoloDeck, Black Box, and negative-authority claims. A generic chaos platform would add cluster credentials, controllers, mutable external state, and a much larger attack surface without solving the content-bound operator ceremony.

The legitimate shortcut is semantic rather than executable: NASA supplies the test-card/readiness boundary; Litmus and Chaos Mesh supply fail-closed probe and abort behavior; AWS FIS supplies terminal stop-condition semantics; and OpenTelemetry supplies interoperable fan and temperature names. The implementation keeps all of those ideas behind `expected_temperature_field_checkride_contract()` so they can be replaced or mapped later.

No third-party code, package, schema, service, credential, key, generated binding, or dataset was incorporated. The installed OpenSSH verifier remains the only adopted external executable in this trust chain, behind the existing TruePanel-owned verifier interface.

## Rejected candidates and failed approaches

- **Deploy LitmusChaos or Chaos Mesh:** rejected because Kubernetes control planes, credentials, CRDs, agents, and fault-injection authority violate the narrow offline/passive boundary.
- **Use AWS FIS directly:** rejected because it is cloud-specific, proprietary, and necessarily grants experiment authority that this increment must not possess.
- **Treat planning approval as execution approval:** rejected because the authenticated appraisal explicitly grants planning eligibility only.
- **Let the plan capture from BattleStation:** rejected because a plan generator must remain unable to access a live host or create a recording.
- **Use descriptive prose for aborts:** rejected because removing or relaxing one exact abort must change the contract and fail closed.
- **Trust a receipt digest without reverifying its statement and SSHSIG:** rejected because content identity alone does not authenticate the operator decision.
- **Name telemetry without units or identity limits:** rejected because correlation needs stable comparable signals, while privacy requires pseudonymous roles rather than host or disk identifiers.

## Collaboration opportunity and open risks

The OpenTelemetry hardware semantic-conventions maintainers are the strongest collaboration opportunity. TruePanel can contribute NAS-relevant examples and learn how fan command ratio, fan speed, enclosure temperature, and physical-disk temperature should be modeled without inventing an incompatible vocabulary. The conventions are still marked development, so TruePanel keeps a replaceable owned interface rather than importing generated bindings.

Open risks remain deliberate: no real JT signature, separately confirmed plan, field recording, or field result exists; pseudonymous profile design has not been tested against a real privacy review; and a deterministic fixture cannot establish field accuracy. POSIX file custody is not an independently witnessed transparency log. The next gate must authenticate a separate confirmation over the exact plan digest and still remain unable to capture, deploy, or actuate anything.

## Reproduce

```bash
pytest -q tests/test_aegis_temperature_field_checkride_plan.py tests/test_aegis_temperature_calibration_candidate_appraisal.py
python -c "from truepanel.holodeck.aegis_temperature_field_checkride_plan import run_temperature_field_checkride_plan_checkride as run; print(run()['measurements'])"
python -m truepanel.hangar validate --root .
node --check truepanel/web/static/reliability-view.js
```
