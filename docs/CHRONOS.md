# Project CHRONOS

## Mission

Most dashboards answer what is true now. CHRONOS explores the next operator questions: what changed, what happened first, which changes are probably related, whether the situation is improving or degrading, what should happen next if recovery is working, and what observation would prove the conclusion wrong.

CHRONOS is a temporal-reasoning layer, not an autonomous repair system.

## Inputs

- OBSERVATORY normalized workload and activity observations
- ORACLE baselines, trends, and anomaly state
- explicit Health Intelligence findings
- AEGIS correlation and confidence
- Pathfinder recovery state and verifiers
- Black Box state transitions
- HoloDeck deterministic rehearsals
- bounded historical telemetry

Every narrative statement retains provenance and time ordering.

## Output contract

A candidate narrative is compact in Pilot mode and expandable in Flight Engineer. It reports CHANGED, LIKELY RELATION, DIRECTION, EXPECTED NEXT, and PROOF.

The wording distinguishes chronology from causality. Followed is not caused by. Causal language requires an existing evidence policy or an explicit confidence qualifier.

## Minimal vertical slice

1. Define a normalized timeline event with timestamp, source, kind, identity, confidence, and provenance.
2. Build deterministic ordering from an OBSERVATORY plus thermal HoloDeck fixture.
3. Derive a bounded direction: improving, steady, degrading, or unknown.
4. Attach an expected-next observation from an existing recovery verifier or HoloDeck rehearsal.
5. Render a short Pilot summary and an evidence-rich Flight Engineer timeline.
6. Fail closed when clocks, evidence identity, or causal linkage are ambiguous.

## Non-goals

CHRONOS does not invent missing events, convert correlation into certainty, predict exact failure times from insufficient evidence, mutate hardware or storage, or replace AEGIS, Pathfinder, or ORACLE.

Its value is sequence, context, and falsifiable expectations.
