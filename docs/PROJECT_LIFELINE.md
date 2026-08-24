# Project Lifeline

Project Lifeline turns TruePanel's fault guidance into a persistent guided-repair session.

The project rule is simple:

> Detect -> Explain -> Diagnose -> Prepare -> Repair -> Verify -> Close

Lifeline is designed around the idea that recognizing a failure is only half of maintenance. The operator should know what TruePanel observed, what is safe to check, what must be verified before physical service, what a valid replacement looks like, and what evidence proves recovery succeeded.

## Safety boundary

The first Lifeline slice is **planning and guidance**, not storage authority.

It can:

- remember a repair across telemetry changes and Mission Control restarts
- correlate the repair with the fault evidence supplied by Project Kobayashi
- require exact member, VDEV, redundancy, device, and bay evidence
- require a source-backed chassis service profile
- record that the operator reviewed backup state
- validate candidate replacement metadata supplied by a read-only inventory layer
- reject undersized, ambiguous, existing-pool, or preserve-data candidates
- detect an active resilver and force the session into recovery monitoring
- require repeated healthy observations before closing the repair
- preserve completed repair history if the same fault recurs later

It cannot:

- offline a pool member
- wipe a disk
- invoke `zpool replace`
- call the TrueNAS pool-replace API
- remove a device
- change enclosure state
- grant itself storage-write authority

A future guarded-authority project must implement those operations separately.

The runtime contract makes this distinction explicit:

- `write_preconditions_complete` means all planning prerequisites for a future guarded write have been satisfied.
- `can_execute_replacement` is always `false` in this Lifeline slice.

## Persistent repair ledger

Default path:

```text
/var/lib/truepanel/lifeline/sessions.json
```

The ledger is TruePanel metadata only. It is written atomically with mode `0600` and records:

- original fault identity
- repair attempt number
- repair-session state
- selected model-specific service provenance
- operator backup-state acknowledgement
- replacement-candidate assessment
- recovery progress
- consecutive healthy verification observations
- completed repair state

The original fault identity is retained intentionally. Linux device names can be reused after media removal or hot-swap, so a later device appearing as `/dev/sdc` must not silently rewrite the identity of the disk that originally failed.

Repeated failures are preserved as separate attempts, for example:

```text
drive:HDDs:raidz1-0:sdc:attempt-1
drive:HDDs:raidz1-0:sdc:attempt-2
```

A completed attempt remains in repair history when a later attempt opens.

## Drive-repair phases

The deterministic drive session uses these phases:

1. `diagnose`
2. `identify`
3. `prepare`
4. `service_ready`
5. `validate_replacement`
6. `replacement_ready`
7. `monitor_recovery`
8. `verify`
9. `complete`

The current evaluator can skip phases when telemetry already proves their prerequisites. It never skips safety gates, and the normal repair path is monotonically ordered.

## Repair gates

A drive repair tracks seven independent gates:

| Gate | Meaning |
| --- | --- |
| `member_identity` | Pool, VDEV, logical device, and unhealthy ZFS state agree. |
| `redundancy` | VDEV topology and remaining fault tolerance are understood. |
| `physical_identity` | Hardware inventory independently maps the logical member to a bay. |
| `service_procedure` | A source-backed procedure matches the configured chassis model. |
| `backup_acknowledgement` | The operator has explicitly reviewed backup state. |
| `replacement_candidate` | Replacement media satisfies validation requirements. |
| `replacement_confirmation` | Reserved for a future guarded write-capable workflow. |

The final gate does **not** create write authority. In this Lifeline slice it marks only the boundary a later project would have to cross.

## Model-specific service profiles

Lifeline does not infer a service procedure from bay count, DMI fragments, branding, or visual similarity.

A deployment must explicitly configure both a known profile and a covered exact model. The first registry entry is the QNAP TVS-x71 family:

```yaml
hardware:
  lifeline:
    service_profile: qnap-tvs-x71
    chassis_model: TVS-671
```

The profile covers:

- TVS-471
- TVS-671
- TVS-871

Its physical-service provenance is the **QNAP TVS-x71 Series Hardware User Manual**.

The profile does not import QTS storage-management procedures. On a QNAP chassis running TrueNAS:

- TrueNAS documentation governs pools, VDEVs, offline/replace semantics, and resilver behavior.
- QNAP hardware documentation governs chassis access, drive bays, serviceability, and hardware safety.
- TruePanel combines both only after the actual machine identity and fault evidence are known.

## Backup-state acknowledgement

Mission Control exposes one Lifeline POST endpoint in this slice:

```text
POST /api/v1/lifeline/acknowledge
```

It only records a backup-state review acknowledgement for an existing Lifeline session.

The request requires:

- same-origin custom intent header `X-TruePanel-Intent: lifeline-backup-ack`
- acknowledgement name `backup_state`
- confirmation token `ACKNOWLEDGE_BACKUP_STATE`
- an existing session ID

The response explicitly reports `hardware_mutation: false`.

No disk offline, replace, wipe, force, or other storage action is accepted by this endpoint.

## Replacement validation

The replacement-assessment contract rejects a candidate when any of these are true:

- capacity is unknown
- capacity is smaller than the failed member
- the candidate belongs to an existing pool
- the candidate contains data the operator intends to preserve
- identity is ambiguous

Multiple candidates remain ambiguous unless exactly one is explicitly selected by the read-only inventory/selection layer.

## Recovery monitoring

An active resilver immediately overrides normal service planning.

While recovery is active, Lifeline reports `monitor_recovery` and prevents physical-service or replacement planning from being considered ready. Mission Control should prominently warn against removing another member of the affected VDEV.

## Recovery verification

The session does not disappear when the original fault card clears.

When the affected pool returns ONLINE and no resilver is active, the ledger enters `verify`. Three consecutive healthy observations are required before the repair is marked `completed`.

Any intervening degraded observation resets the healthy counter to zero.

This protects against a one-sample green flash being mistaken for a completed repair.

## HoloDeck acceptance mission

`tests/test_lifeline_drive_repair_acceptance.py` exercises the complete deterministic repair arc:

```text
FAULTED member
    -> exact evidence
    -> chassis procedure verified
    -> backup state acknowledged
    -> undersized replacement rejected
    -> valid replacement accepted for planning
    -> storage-write boundary remains locked
    -> resilver monitoring
    -> three healthy verification samples
    -> repair complete
    -> service restart retains closed session
```

## Next expansion

Once this slice is accepted, the same repair-session engine should be applied to:

- fan replacement
- cooling emergencies
- network-link diagnosis
- LCD/controller recovery
- telemetry-source failures

The next major knowledge-layer project should expand the service-profile registry to additional QNAP families and community hardware without weakening the rule that model-specific repair steps require model-specific evidence.
