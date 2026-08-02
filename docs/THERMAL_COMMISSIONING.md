# Thermal Control Commissioning

## Commissioned State

TruePanel supervised thermal control completed live commissioning on August 2, 2026.

Commissioned truepanel.yaml SHA-256:

d31e6f1707ec39c8a89be7243758663b196462005ef1e394b84eeeff1dbe10b1

Runtime operator authorization remains ephemeral and is not restored after a service restart.

## Live Lifecycle Coverage

- supervised_started
- supervised_expired
- supervised_disarmed
- supervised_safety_cancelled

Every trial ended with both controlled fan channels restored to motherboard Automatic control.

## Proven Safety Contracts

Live commissioning verified that TruePanel:

- starts supervised live control only from a valid Balanced recommendation;
- restricts supervised live control to the Balanced profile;
- uses a bounded 120-second supervised lease;
- restores motherboard Automatic on manual disarm, lease expiry, and safety cancellation;
- returns to dry-run and operator-disarmed state after a supervised session;
- records commissioning lifecycle events durably;
- exposes commissioning history through Mission Control;
- does not persist runtime operator authorization across service restart.

## Commissioning Evidence

Lifecycle history:

/var/lib/truepanel/history/thermal-commissioning.jsonl

Read-only Mission Control endpoint:

GET /api/v1/fans/commissioning-history

## Current Operational Boundary

This commissioning proves the bounded supervised-control contract. It does not authorize indefinite automatic fan control.

The next rollout stage must remain lease-bound, fail safe to motherboard Automatic, and initially exclude automatic Afterburners selection.
