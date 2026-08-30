# AEGIS field-evidence gate

AEGIS must not confuse a perfect result on a small deterministic fixture set
with production validation. `aegis-field-evidence-gate-v1` turns that rule into
a machine-verifiable contract.

## Admission contract

A field corpus is admissible only when its dataset card declares:

- operator opt-in collection authority;
- sanitized data with no retained raw identifiers;
- approved review state and human-reviewed incident outcomes;
- calibration as an allowed use;
- a retention policy; and
- a system profile, workload class, and reviewed label for every recording.

The contract records roles and factual decisions, not contributor names. Black
Box's byte limits, digests, path containment, monotonic replay, and at-rest
sanitizer comparison remain mandatory underneath this gate.

## Statistical promotion contract

Point estimates are insufficient for small or extreme samples. AEGIS computes
two-sided 95% Wilson score bounds and requires all of these before a corpus can
become a `field_candidate`:

| Gate | Floor |
| --- | ---: |
| Positive reviewed recordings | 5 |
| Negative reviewed recordings | 20 |
| System profiles | 2 |
| Workload classes | 4 |
| False-positive-rate 95% upper bound | at most 1% |
| Recall 95% lower bound | at least 80% |

These are explicit version-one policy thresholds, not universal statistical
truths. They are deliberately conservative and replaceable.

The current synthetic corpus observes 0 false-positive frames among 141
negative frames and detects its one positive recording. Its Wilson bounds are
nevertheless 2.6522% for the false-positive upper bound and 20.6549% for the
recall lower bound. It therefore remains `lab_calibrated` with eight HOLD
reasons.

Even a corpus satisfying every automated gate is only a `field_candidate`.
`production_validated` remains false until an explicit release review issues a
separate promotion decision. The evidence gate has no repair, deployment, or
hardware-control authority.

## Replaceable detector benchmark

The HoloDeck corpus runner now accepts a TruePanel-owned `IncidentDetector`
factory. The built-in declarative policy is one adapter; future detectors can
run through the identical ordered recordings and metrics without changing the
corpus, Mission Control, or authority model.

Preserved evidence:

- [`evidence/aegis-field-evidence-gate-v1.json`](evidence/aegis-field-evidence-gate-v1.json)
- [`evidence/aegis-black-box-corpus-v1.json`](evidence/aegis-black-box-corpus-v1.json)
