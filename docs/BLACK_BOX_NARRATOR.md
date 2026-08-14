# Black Box Incident Narrator

The Black Box incident narrator turns adjacent privacy-sanitized replay frames into a compact, deterministic timeline of observed state changes.

It is intended for support, replay fixtures, and future Digital Twin tooling. The narrator is deliberately evidence-bound: it reports what changed in the recording and does not claim to know why it changed.

## Current narrated transitions

The first version recognizes:

- storage health/status/state changes;
- fan RPM transitions to zero and recovery from zero;
- alert appearance and clearance;
- Mission Control availability/health transitions;
- LCD availability and stale/fresh transitions; and
- increases in recorded front-panel button reports.

Normal LCD page rotation is intentionally not narrated as an incident. That keeps routine Flight Deck movement from overwhelming operational events.

## Safety boundary

Narration operates only on an already-validated `BlackBoxReplay` containing privacy-sanitized `BlackBoxFrame` objects.

It does **not**:

- read hardware or sysfs;
- open the A125 serial controller;
- use LCD or fan command sockets;
- activate the standalone Host Agent;
- restart services;
- query the live Mission Control runtime;
- call external or AI services; or
- execute callbacks supplied by a recording.

Summaries are passed through the Black Box sanitizer again before being emitted, line breaks are flattened, and both event count and summary length are bounded.

## Interpretation contract

Narration describes observations rather than causes. For example, a pool-health field changing from `ONLINE` to `DEGRADED` is reported as a storage-health change. The narrator must not invent a failed disk, cable problem, controller fault, or repair action unless that fact is explicitly represented by a future validated recording field.

This separation is intentional: Black Box can become a useful incident flight recorder without becoming an authority for hardware actuation or speculative diagnosis.
