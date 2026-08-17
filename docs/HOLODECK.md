# Project HoloDeck

HoloDeck is TruePanel's deterministic, hardware-isolated Digital Twin. It
runs real TruePanel presentation and health code against sanitized simulated
host state so failures can be reproduced without putting a NAS in the loop.

## Safety boundary

HoloDeck providers never construct production hardware controllers. The
provider exposes a deny-all hardware boundary whose device, sysfs, command,
and arbitrary actuator entry points raise `SimulationSafetyError`. Fixtures
are always marked `simulation: true` and `read_only: true`.

The first composition seam is Mission Control's `SnapshotService`. HoloDeck
injects both collector and fan telemetry providers, plus a deterministic
clock. Production collector and hardware defaults remain unchanged.

## Quick start

Run the built-in privacy-safe BattleStation profile:

```console
python3 truepanel.py holodeck run battlestation --steps 3
```

Emit complete Mission Control API snapshots:

```console
python3 truepanel.py holodeck run battlestation --steps 3 --json
```

Replay a privacy-safe Black Box recording through the same Mission Control
snapshot and Health Intelligence pipeline:

```console
python3 truepanel.py holodeck replay incident.jsonl --json
```

Apply a fault to a fresh twin and inspect the resulting state:

```console
python3 truepanel.py holodeck inject fan_stall channel=1
python3 truepanel.py holodeck inject disk_fault bay=4
python3 truepanel.py holodeck inject network_down interface=enp116s0
python3 truepanel.py holodeck inject temperature sensor=cpu value=92
python3 truepanel.py holodeck inject lcd_disconnect
```

Evaluate the built-in safety invariants across a bounded scenario run:

```console
python3 truepanel.py holodeck check battlestation \
  --scenario tests/fixtures/scenarios/everything-is-on-fire.yaml \
  --steps 8 --step-seconds 10 --json
```

The report is deliberately compact. It contains rule identifiers, observation
indexes, and bounded evidence only; it never prints raw host state, snapshots,
or Black Box frames. Runs are limited to 1,000 observations and return status
0 when every invariant passes or status 1 when a violation is found.

Compile a recorded violation into sanitized, data-only regression material:

```console
python3 truepanel.py holodeck compile-incident incident.jsonl \
  --invariant cooling.stalled_not_healthy \
  --output compiled-incident.json
```

The complete scenario and manifest are written only to the explicitly named
output file. Standard output receives the compact manifest, not recorded
frames. Compilation is capped at 10,000 input frames and 1,000 evaluator
calls, reports budget exhaustion, sanitizes the artifact again, and refuses to
overwrite an existing file. The compiler generates no executable code.

## Scenario files

YAML and JSON scenario documents contain a host name and time-ordered events:

```yaml
name: thermal-and-fan-failure
host: battlestation
events:
  - at: 10
    type: temperature
    sensor: cpu
    value: 78
  - at: 20
    type: fan_stall
    channel: 1
```

Run one with:

```console
python3 truepanel.py holodeck run battlestation \
  --scenario tests/fixtures/scenarios/everything-is-on-fire.yaml \
  --steps 8 --step-seconds 10 --json
```

Supported events currently include temperature changes, fan stall/recovery,
disk fault/removal, network up/down, LCD connect/disconnect, telemetry
freshness, and pool-health changes.

## Whole-stack failure stories

`HoloDeckScenarioRunner` composes the simulated host with TruePanel's real
thermal policy, debounced fan-health watcher, stateful storage-health watcher,
Mission Control snapshot service, and Health Intelligence. Its LCD and runtime
status bridges are rooted in a caller-supplied temporary directory; production
hardware managers and production `/run` and `/var` paths are never used.

One deterministic `step()` returns the raw simulated state, thermal
recommendation, emitted Mission Events, and final Mission Control snapshot.
The regression suite covers a fan stall during rising temperature, a faulted
drive bay, loss of the primary network link, LCD disconnection, and stale
thermal telemetry. Fan alerts retain the production three-observation debounce,
and stale telemetry fails safe by recommending motherboard Automatic control.

## Current boundary and next steps

The current foundation exercises deterministic scenario state, Black Box
recording replay, the real Host Agent safety/fan lifecycle, Mission Control,
Health Intelligence, thermal policy, and production watcher behavior. All fan
decisions are applied only to the in-memory twin.

The remaining integration slices are:

1. Start an embedded Mission Control server on an ephemeral port for real HTTP
   smoke tests where the execution sandbox permits sockets.
2. Converge the older Black Box chaos vocabulary with HoloDeck's channel-,
   bay-, interface-, and sensor-specific scenario events.
3. Add incident-to-regression tooling: recording, replay, fault mutation,
   fixed behavior, and proof of non-regression.
