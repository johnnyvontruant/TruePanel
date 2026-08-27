# Mission Control and Reliability

Mission Control is TruePanel's browser-based operational cockpit. It turns raw host and hardware telemetry into an ordered view of current condition, evidence, recovery guidance, and verification state without taking direct ownership of the front-panel controller or privileged Host hardware boundary.

## What the operator sees

Mission Control is organized around a simple priority:

1. what needs attention now;
2. why TruePanel believes it matters;
3. the safest useful next action;
4. how recovery will be verified;
5. deeper telemetry and history when needed.

The dashboard combines:

- system health and service state;
- CPU, memory, network, pool, drive, fan, and thermal telemetry;
- the live Virtual Front Panel;
- Preflight readiness;
- Health Intelligence findings;
- guided recovery sessions;
- storage-specific Lifeline evidence;
- AEGIS reliability correlation on development builds;
- history, commissioning evidence, and diagnostics.

The layout is explicitly responsive. At narrow widths, including phones, primary status, evidence, recovery, and reliability sections collapse into a single readable column without requiring horizontal scrolling.

## Service boundary

Mission Control runs independently as `truepanel-mission-control.service`. Restarting it does not restart the primary LCD service.

The web process may read normalized TruePanel state and, when explicitly enabled, persist a narrow set of validated configuration fields. HTTP handlers do not directly write serial commands, I2C registers, fan sysfs controls, bay LEDs, storage state, or network configuration.

The Virtual Front Panel follows the same rule. ENTER and SELECT requests travel through a local Unix socket to the ordered LCD dispatcher. Mission Control never opens the A125 serial device.

## Status and access

Check the service from the installed CLI:

```bash
truepanel mission-control status
```

The local dashboard and status API are:

```text
http://127.0.0.1:8787
http://127.0.0.1:8787/api/v1/status
```

Mission Control is localhost-bound and read-only by default.

For access from a trusted LAN or Tailscale network, set the service bind address in `/etc/default/truepanel-mission-control`:

```text
TRUEPANEL_MC_HOST=0.0.0.0
```

Then restart only Mission Control:

```bash
sudo systemctl restart truepanel-mission-control.service
```

Binding to `0.0.0.0` exposes the service on every available interface. Use trusted network boundaries, firewall policy, or an authenticated reverse proxy appropriate for the deployment. TruePanel does not treat network reachability as authentication.

## Preflight

Preflight provides an on-demand readiness picture across:

- Host
- Storage
- Cooling
- Front Panel
- Safety Interlocks

Individual checks report `PASS`, `REVIEW`, or `FAIL`. The overall projection uses `READY`, `REVIEW`, or `HOLD`.

A `REVIEW` result is intentionally visible. It means the available evidence needs operator interpretation; it is not silently converted into a pass. Preflight is passive and does not grant hardware-control authority.

Mission Control can also produce the same privacy-safe compatibility support bundle used by the CLI. The bundle excludes hostnames, addresses, hardware identifiers, credentials, configuration secrets, and pool contents.

## Health Intelligence

Health Intelligence converts normalized telemetry into conservative findings for:

- cooling and fan state;
- high temperature;
- SMART and physical-media warnings;
- faulted disks and degraded pools;
- primary network-link loss;
- unavailable or stale front-panel state;
- stale telemetry;
- TruePanel service health.

Unknown or missing evidence remains unknown. A missing signal is not automatically treated as healthy.

Each actionable finding carries a stable guidance code and evidence suitable for the recovery layer. TruePanel retains the underlying alert even when a higher-level incident summary is available.

## Pathfinder guided recovery

Project Pathfinder owns the stateful recovery workflow.

A recovery path can move through:

```text
detected -> diagnosing -> ready for action -> verifying -> resolved
```

The exact phases may vary with the fault, but the contract is consistent:

- explain the detected condition;
- show the evidence TruePanel used;
- distinguish passive checks from physical or disruptive actions;
- present immediate stabilization guidance;
- guide diagnosis and repair;
- define machine-verifiable recovery criteria;
- preserve the result in the recovery timeline.

Pathfinder does not infer that a repair succeeded merely because an alert disappeared. Resolution requires the fault-specific verifier to evaluate the recovered telemetry or subsystem state.

Potentially destructive storage work remains a guarded human operation. Mission Control can explain the safe sequence and verify observations, but it does not replace TrueNAS storage authority.

## Lifeline storage recovery

Project Lifeline is the deeper storage-recovery path used when evidence indicates a replacement-worthy physical-media problem.

Lifeline joins SMART evidence with verified ZFS and physical-bay identity, fails closed when ownership or identity is ambiguous, and preserves the relationship among:

- pool and vdev;
- logical device;
- physical bay;
- model and relevant health evidence;
- the guarded replacement or recovery procedure;
- post-action verification.

The goal is to make hardware replacement approachable without encouraging blind disk removal or destructive pool commands. SMART recovery remains in verification until critical SMART evidence is clear and the independently observed ZFS member state is explicitly `ONLINE`.

## ORACLE predictive health

Project ORACLE learns a component's normal behavior and evaluates rolling statistics, trends, and cross-signal relationships. Baseline learning is limited to one sample per telemetry interval, independent of browser request volume; Mission Control reuses the primary status stream instead of adding a recurring reliability poll.

ORACLE states such as `WATCH` or `DEVELOPING` are predictive observations, not production hard-fault authority. Statistical drift cannot invent a failed disk, stalled fan, or overheated system without an independent detector.

Current limitations include in-memory baselines and the need for calibration against a broader corpus of sanitized Black Box recordings.

## AEGIS reliability correlation

Project AEGIS connects ORACLE, Pathfinder, Lifeline, HoloDeck, and Black Box into a read-only reliability-intelligence layer.

AEGIS can group related evidence into one probable root-cause hypothesis while retaining all contributing alerts. The Reliability view shows:

- the active consolidated incident;
- likely cause;
- confidence and supporting signals;
- the safest next action;
- verification state;
- Recovery Coverage Matrix gaps.

Confidence measures mutually supporting evidence, not causal certainty. User-facing language must continue to say “likely cause” or “hypothesis.”

AEGIS has no fan, LCD, bay LED, storage, network, service, boot-task, or configuration write path.

The accepted AEGIS development increment proved a shared-cooling scenario in HoloDeck:

- probable shared cause identified at sample 19;
- first isolated threshold at sample 46;
- 27-sample detection lead;
- two terminal alerts consolidated into one incident;
- 50 percent reduction in operator alert count;
- recovery verification rehearsal passed;
- two privacy-sanitized Black Box frames preserved;
- no production mutation.

AEGIS is accepted in the post-1.2 development line and has not been deployed to the reference NAS.

## Recovery Coverage Matrix

A recovery path is `TRUSTED` only when all required evidence exists:

- declared detector;
- diagnostic evidence fields;
- immediate, diagnostic, corrective, and verification guidance;
- fault-specific automated verifier;
- deterministic regression scenario;
- passed fault-present-to-recovered rehearsal.

The development contract currently covers these guidance codes:

| Guidance code | Recovery focus |
| --- | --- |
| `cooling.fan_stall` | Restore verified fan delivery |
| `thermal.high_temperature` | Reduce and verify thermal state |
| `storage.smart_warning` | Validate media evidence and ZFS identity |
| `storage.disk_faulted` | Guide physical and logical disk recovery |
| `storage.pool_degraded` | Restore and verify pool redundancy |
| `network.link_down` | Restore link and address state |
| `front_panel.lcd_unavailable` | Restore reader and dispatcher health |
| `telemetry.stale` | Restore trustworthy telemetry freshness |

CI fails when a new actionable guidance code is added without its coverage definition, verifier, complete guidance arc, and deterministic scenario.

## HoloDeck and Black Box evidence

HoloDeck runs the real TruePanel health and presentation layers against an in-memory, hardware-isolated host. It is the preferred place to inject faults and rehearse verification logic.

Black Box preserves privacy-sanitized key frames so a decision can be replayed and audited. Evidence frames and reports use deterministic digests to prove that the same inputs produce the same result.

Neither system is permission to experiment against production hardware.

## Configuration writes

Configuration writes remain disabled unless explicitly enabled:

```text
TRUEPANEL_MC_ALLOW_CONFIG_WRITES=true
```

The current write surface is narrow and validated. Saves use atomic replacement and create a timestamped backup. Mission Control does not automatically restart the LCD service after a save.

Keep write mode disabled unless remote configuration is specifically required.

## Operator rules

- Treat `REVIEW` and `UNKNOWN` as honest states, not cosmetic warnings.
- Read the evidence before taking a physical action.
- Follow the guidance safety category.
- Keep destructive storage work inside supported TrueNAS workflows.
- Re-run the fault-specific verification after corrective action.
- Do not run direct A125 laboratory commands while `truepanel.service` owns the serial controller.
- Do not use an AEGIS hypothesis as automatic repair authority.
- Preserve mobile usability when changing the cockpit.
