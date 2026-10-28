# AEGIS read-only temperature field checkride

## Outcome

This increment connects the public-only JT signing ceremony to a bounded,
privacy-sanitized Black Box replay. The evaluator independently re-runs the
returned SSHSIG verification, reproduces the missing-temperature incident,
and requires three subsequent complete observations with stable member
identity before it accepts the recovery path for review.

The live Mission Control state remains
`ACTION_REQUIRED_AUTHENTICATED_DEVELOPMENT_ACCEPTANCE`: no JT key, signature,
or field recording is present. A deterministic HoloDeck pass proves only the
mechanics. Even an operator-opt-in field observation reaches only
`FIELD_OBSERVATION_ACCEPTED_FOR_REVIEW`; it cannot validate production,
accept or install the 9/9 candidate, deploy software, write storage or network
state, or actuate hardware.

## Architecture and CI contract

`evaluate_temperature_field_checkride` composes the existing public-kit return
verifier, Black Box sanitization boundary, temperature-blind-spot detector,
and fault-specific three-observation recovery verifier. It requires:

- an exact, current development-only SSHSIG return;
- exactly four bounded sanitized Black Box frames;
- strictly increasing sequence and capture time;
- one reproduced missing-temperature observation;
- an unchanged complete present-member identity set; and
- three consecutive complete identity-matched temperature observations.

Field provenance additionally requires operator opt-in and human outcome
review. Simulation is forbidden from claiming either. Unknown top-level frame
fields, raw identifiers, identity drift, incomplete recovery, replay ordering,
and ungoverned sources fail closed. The CI test replays and compares the exact
preserved evidence document, so the contract cannot change silently.

Mission Control adds a mobile-friendly `Read-only Temperature Field Checkride`
panel showing signature, sanitized-observation, validation, installation, and
authority states. It performs no capture and adds no polling or controls.

## HoloDeck evidence

TP-EXP-0028 preserves twelve scenarios: one deterministic recovery rehearsal,
one operator-opt-in field-shaped fixture accepted for separate review, and ten
HOLD results. Holds cover invalid authentication, unsanitized identity,
non-monotonic replay, incomplete recovery, member drift, missing initial fault,
ungoverned provenance, missing consent, missing outcome review, and simulation
claiming field review.

False field-validation claims, candidate acceptances, installations,
deployments, hardware actions, and runtime writes are all zero. The fixture
key is disposable and removed. Preserved evidence:
`docs/evidence/aegis-temperature-field-checkride-v1.json`, self-digest
`f668dcaaadc348ed3e64140ea45c7eaf5d343f930950a89973e2e0e9fc30b384`.

## Prior-Art Field Report

Actual upstream code and specifications were inspected on 2026-10-13.

| Candidate | Inspected capability and transferable lesson | Fit, maturity, security, and dependency | License / attribution | Decision |
| --- | --- | --- | --- | --- |
| [smartmontools JSON implementation](https://github.com/smartmontools/smartmontools/blob/master/smartmontools/json.h) | Typed JSON tree, deterministic sorted output, and explicit safe-integer handling for hardware evidence | Mature source of SMART telemetry, but direct parser/code reuse would add GPL coupling and platform-specific behavior. TruePanel already owns a provider boundary. | GPL-2.0-or-later; no code copied. | **Adapt the typed, deterministic evidence discipline; do not embed code.** |
| [in-toto Statement v1](https://github.com/in-toto/attestation/blob/main/spec/v1/statement.md) | Immutable digest-bound subjects and an explicit predicate type | Mature attestation design. A new schema/verifier dependency is unnecessary because the signing record already binds exact subjects. | Specification CC-BY 4.0; concept cited, no schema or code copied. | **Adapt subject binding and independent reconstruction.** |
| [Prometheus rule parser](https://github.com/prometheus/prometheus/blob/main/model/rulefmt/rulefmt.go) | Known-field parsing, semantic validation, and template parse tests before alert rules are accepted | Mature, actively maintained validation model. Embedding Prometheus would be disproportionate for four replay frames. | Apache-2.0; no code copied. | **Adapt strict known-field and semantic validation.** |
| [OpenZFS vdev identity](https://github.com/openzfs/zfs/blob/master/include/sys/vdev_impl.h) | `vdev_guid` is explicitly the unique vdev identity, distinct from child number and aggregate GUIDs | Strongest future stable-identity source for TrueNAS topology. Direct kernel coupling is unsafe; use only a supported passive middleware field when available. | CDDL-1.0; no code copied. | **Adapt the stable-identity concept; defer integration.** |
| [OpenTelemetry semantic conventions](https://github.com/open-telemetry/semantic-conventions) | Namespaced, versioned telemetry attributes and resource identity conventions | Broad, mature interoperability model, but no current NAS member-temperature convention supplies TruePanel's exact recovery semantics. | Apache-2.0; no code or dependency added. | **Use as architectural inspiration; defer SDK adoption.** |

No external code, package, schema, service, credential, key, or dataset was
incorporated. The strongest collaboration opportunity is TrueNAS/OpenZFS
maintainers: a supported passive leaf-vdev GUID in the middleware topology
would replace device-name stability assumptions without kernel coupling.

## Failed paths and open risks

- Trusting a copied authentication-result mapping was rejected; the field
  evaluator re-runs exact kit and SSHSIG verification.
- Letting Black Box sanitize during admission was rejected because it could
  conceal that raw identifiers reached the boundary; supplied and re-sanitized
  frames must be byte-for-byte equivalent as data.
- A single healthy frame was rejected as recovery proof; all three complete
  observations must share the exact present-member identity set.
- A simulation labeled as field-reviewed is rejected even when its telemetry
  is otherwise valid.
- Device name plus physical bay is still weaker than a supported leaf-vdev
  GUID. The checkride therefore accepts evidence only for review and never
  installs the candidate.

The next gate is external: JT provisions the protected development public
roster, signs the exact public kit offline, and returns only the SSHSIG. A
separately authorized, operator-opt-in sanitized recording can then exercise
this read-only checkride. Deployment remains a different future decision.
