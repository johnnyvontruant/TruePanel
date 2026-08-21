# Mission Control Operator Guidance

TruePanel should not stop at detecting a fault. For every fault that Mission Control can identify with useful confidence, the operator should receive a safe path from detection to recovery.

The core contract is:

**Detect -> Explain -> Diagnose -> Resolve -> Verify**

A fault is not considered fully implemented until TruePanel can both identify the condition and present a useful recovery path.

## Design goals

Operator guidance should:

- describe what TruePanel actually observed rather than display a generic error;
- distinguish related but different conditions, such as a SMART warning, ZFS I/O fault, missing disk, and degraded pool;
- surface immediate risk and remaining redundancy before suggesting physical action;
- prefer safe external checks before invasive service steps;
- clearly mark shutdown-required, caution, and destructive actions;
- adapt hardware instructions to the detected chassis/model when authoritative documentation exists;
- use TrueNAS guidance for ZFS/pool operations and hardware-vendor guidance for physical chassis operations;
- verify recovery from live telemetry instead of asking the operator to assume a repair worked;
- preserve provenance so Mission Control can show where a procedure came from and what versions/models it applies to.

## Guidance-card contract

Each Mission Control fault card should be able to render these sections.

### What happened

A short plain-language description of the observed condition.

### Severity

Suggested presentation levels:

- **Advisory**: degraded convenience or noncritical subsystem with no immediate system risk.
- **Caution**: operator attention is needed, but the system has not yet entered a critical failure state.
- **Warning**: redundancy, cooling, or data safety is materially reduced and prompt action is appropriate.
- **Critical**: data availability, thermal safety, or continued operation is at immediate risk.

Severity should be derived from live context. A failed fan while temperatures are stable is different from a failed fan while temperatures are rapidly climbing.

### What TruePanel knows

Display evidence that supports the diagnosis. Examples include:

- affected fan label/channel and current RPM;
- expected RPM range and failed-observation count;
- CPU/system temperature and trend;
- pool, VDEV, topology, remaining redundancy, and resilver state;
- exact disk bay, device, model, capacity, presence, and serial suffix;
- SMART event separately from ZFS read/write/checksum error state;
- interface carrier/operstate separately from IP-address state;
- LCD serial-device state, last successful I/O, reader state, and dispatcher state;
- telemetry age, missing domains, Host Agent state, and safety/control state.

### What this means

Explain impact in plain language without overstating certainty. Prefer wording such as "cooling redundancy is reduced" over "the NAS will overheat" when temperature remains normal.

### What to do now

Start with low-risk actions. Examples include confirming backups, checking alternate management access, clearing external airflow obstruction, or preserving a healthy network path.

### Diagnose

Guide the operator through narrowing the cause. A useful flow separates similar failure layers before replacement is suggested.

### Resolve

Provide a repair route with explicit risk labels. A card must never hide a destructive operation behind a neutral button.

### Verify

TruePanel should observe the repaired condition and confirm that the system has recovered. A repair card should not clear merely because the operator clicked "done."

### Escalate when

Define the boundary where TruePanel should stop giving routine repair guidance and recommend qualified service, backup restore, or deeper investigation.

## Risk vocabulary

The initial catalog uses three action-risk classes:

- `safe`: observation, external inspection, or a reversible non-destructive step;
- `caution`: a step that can affect service availability or requires careful hardware handling;
- `destructive`: a step that can destroy existing data or materially change storage state.

The catalog also records `requires_shutdown` and `destructive` independently so the UI can apply explicit confirmations.

## Initial fault families

| Fault code | Initial severity | Primary operator outcome |
| --- | --- | --- |
| `cooling.fan_stall` | Warning | Stabilize thermal risk, distinguish stall from telemetry loss, use model-specific service guidance, verify RPM recovery |
| `thermal.high_temperature` | Warning | Reduce load, correlate airflow/fan state, correct cooling cause, verify sustained temperature recovery |
| `storage.smart_warning` | Caution | Separate drive-health warning from ZFS fault state, protect backups, determine replacement urgency |
| `storage.disk_faulted` | Warning | Protect remaining redundancy, identify exact bay, replace safely, monitor resilver, verify ONLINE state |
| `storage.pool_degraded` | Warning | Resolve the degraded VDEV/member cause before physical action and route to the specific repair |
| `network.link_down` | Caution | Preserve alternate access, isolate physical-link versus address/configuration failure, restore and verify connectivity |
| `front_panel.lcd_unavailable` | Advisory | Keep NAS management available, isolate serial/service/controller failure, restore the narrowest component first |
| `telemetry.stale` | Caution | Enter fail-safe decision behavior, find the stale producer, restore fresh observations, verify safety-policy recovery |

## Storage guidance boundaries

Storage guidance is where source separation matters most.

### TrueNAS owns storage semantics

For TrueNAS 25.10, official documentation describes drive health as a combination of real-time ZFS failure detection and middleware SMART polling. These are related signals, but they are not interchangeable.

TrueNAS documentation also establishes that:

- a failed disk should be replaced promptly to restore redundancy;
- a replacement disk must be the same capacity or larger;
- replacement automatically starts a resilver;
- a replacement operation can fail when the candidate contains partitions/data;
- the `Force` option can permit replacement by destroying existing contents on the selected replacement disk;
- operators should wait for resilver completion before replacing another disk.

Mission Control should therefore never reduce `SMART warning`, `ZFS FAULTED`, `device missing`, and `pool DEGRADED` to a single generic "bad drive" state.

### The hardware vendor owns chassis semantics

QNAP documentation should be used for model/chassis facts such as:

- drive-bay count and physical service layout;
- whether a model family supports hot-swappable drives;
- hardware safety warnings;
- service access and physical handling constraints.

QNAP QTS storage-management steps must not be copied into TruePanel as the storage workflow on a TrueNAS installation. TrueNAS remains authoritative for ZFS and pool management.

For the TVS-x71 family, the QNAP hardware manual lists TVS-471, TVS-671, and TVS-871 among systems that support hot-swappable drives under the documented redundant RAID conditions. The same manual also warns about electrical/physical service risk. Mission Control should therefore show model-specific physical guidance and retain a shutdown/service warning when appropriate rather than blindly issuing a universal hot-swap instruction.

## HoloDeck acceptance relationship

The built-in HoloDeck missions currently map to guidance as follows:

- `thermal-ramp` -> `thermal.high_temperature`
- `fan-stall-recovery` -> `cooling.fan_stall`
- `drive-failure` -> `storage.disk_faulted`, `storage.pool_degraded`
- `drive-failure-recovery` -> `storage.disk_faulted`, `storage.pool_degraded`
- `drive-removal` -> `storage.pool_degraded`
- `drive-removal-reinsert` -> `storage.pool_degraded`
- `network-flap` -> `network.link_down`
- `lcd-loss-recovery` -> `front_panel.lcd_unavailable`
- `stale-telemetry-recovery` -> `telemetry.stale`

Tests require every built-in HoloDeck mission to have at least one guidance entry. This turns operator guidance into part of the acceptance surface rather than optional documentation.

## Recommended HoloDeck fault expansion

The next simulation wave should add event primitives and missions for conditions that are not yet directly represented by the current nine missions:

1. SMART warning without a ZFS fault.
2. Rising ZFS read/write/checksum errors before a terminal FAULTED state.
3. Network link negotiated below expected speed while carrier remains up.
4. Fan telemetry channel missing while other hwmon telemetry remains fresh.
5. Multiple simultaneous fan failures.
6. High temperature plus fan failure to test context-sensitive severity.
7. Replacement disk too small.
8. Replacement disk contains existing data and requires explicit destructive-force handling.
9. Resilver in progress, including prohibition on a second replacement.
10. Host Agent unavailable while Mission Control remains reachable.
11. LCD malformed response/timeout distinct from physical serial-device disappearance.
12. Multi-fault `apocalypse` mission combining storage, cooling, network, and telemetry faults while asserting prioritization and recovery behavior.

Each new event should include deterministic time semantics and a recovery event so HoloDeck can test both fault entry and fault exit.

## Mission-report extension

A future HoloDeck mission report should expose operator-guidance acceptance explicitly, for example:

```text
TRUEPANEL HOLODECK MISSION REPORT

Scenario: fan-stall-recovery

PASS  Fan failure detected after debounce
PASS  Cooling degradation visible in Mission Control
PASS  Guidance code cooling.fan_stall selected
PASS  Immediate safe actions present
PASS  Remediation risk classified
PASS  Recovery verification present
PASS  Fan recovery emitted once
PASS  Guidance clears only after sustained recovery

Result: PASS
```

A useful machine-readable report field would be:

```json
{
  "operator_guidance": {
    "passed": true,
    "fault_codes": ["cooling.fan_stall"],
    "checks": [
      "guidance_present",
      "evidence_complete",
      "remediation_risk_classified",
      "verification_present",
      "recovery_observed"
    ]
  }
}
```

## Provenance and compatibility metadata

Before guidance is rendered as an authoritative step-by-step repair procedure, entries should gain compatibility metadata such as:

- TrueNAS release range;
- hardware manufacturer;
- chassis/model family;
- hardware revision when necessary;
- source document title and revision/date;
- whether the instruction is generic, model-specific, or installation-specific;
- whether the procedure has been validated in HoloDeck only or on physical hardware.

Mission Control should be able to show a compact provenance footer such as:

`Verified for TrueNAS 25.10 / QNAP TVS-671. Sources: TrueNAS Documentation, QNAP TVS-x71 Hardware User Manual.`

## Initial authoritative sources

- TrueNAS 25.10 Drive Health Management: <https://www.truenas.com/docs/scale/25.10/scaletutorials/scaletutorialsprint/#drive-health-management>
- TrueNAS 25.10 Managing Pools: <https://www.truenas.com/docs/scale/25.10/scaletutorials/storage/managepoolsscale/>
- TrueNAS API v25.10.4 `pool.replace`: <https://api.truenas.com/v25.10/api_methods_pool.replace.html>
- QNAP TVS-x71 Series Hardware User Manual: <https://download.qnap.com/TechnicalDocument/QNAP_TVS-x71-QNAP_Turbo_NAS_Hardware_Manual_ENG_20150330.pdf>

## Implementation order

1. Keep the guidance catalog data-only and read-only.
2. Add Mission Control API serialization for guidance cards.
3. Bind existing watcher/health events to fault codes.
4. Add evidence adapters that populate fault-specific live context.
5. Add UI rendering with risk badges and source provenance.
6. Add explicit confirmation gates for destructive operations.
7. Expand HoloDeck fault primitives and recovery scenarios.
8. Add operator-guidance acceptance to HoloDeck mission reports.
9. Add model-specific hardware profiles as authoritative documentation is collected and validated.
10. Only then consider guided one-click actions, with existing TruePanel safety authority preserved.

The intended end state is simple: if TruePanel knows enough to raise a fault, Mission Control should also know enough to give the operator a credible next step, or clearly explain why escalation is required.
