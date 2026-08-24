# Project Lifeline Live Test Plan

This checklist is the guarded path for validating Project Lifeline on BattleStation after CI certification.

## Safety rule

Live testing begins read-only and advances one hardware boundary at a time.

The following remain out of scope for this test cycle:

- offlining a pool member
- `zpool replace`
- TrueNAS `pool.replace`
- wiping or partitioning a disk
- removing a healthy pool member
- changing ZFS topology
- enabling any generic browser-supplied bay control

If storage health, bay identity, service-profile identity, or the expected deployment state is ambiguous, stop the test and return to diagnosis.

## Gate 0: establish the baseline

Before deploying the Lifeline branch:

1. Record the currently deployed TruePanel version and commit.
2. Confirm both TruePanel services are active.
3. Confirm the production configuration has a backup.
4. Confirm the HDD pool is healthy and no resilver or scrub recovery is active.
5. Confirm all expected pool members are present.
6. Record the current enclosure/bay mapping.
7. Confirm Mission Control is healthy before any Lifeline code is introduced.

Expected result: a known-good rollback point and a healthy storage baseline.

## Gate 1: deploy without storage authority

Deploy the certified Project Lifeline head using the existing guarded TruePanel lifecycle workflow.

Do not add or enable any storage-write capability. Lifeline must remain planning/guidance only.

Verify:

- `truepanel.service` is active.
- `truepanel-mission-control.service` is active.
- Mission Control responds normally.
- existing fan, LCD, network, storage, and health telemetry remain intact.
- the Lifeline ledger path can be created without affecting normal telemetry.

Expected result: existing TruePanel behavior is unchanged except for additive Lifeline fields/assets.

## Gate 2: healthy-system observation

With BattleStation healthy, inspect `/api/v1/status` and the Mission Control Flight Manual.

Verify:

- `lifeline.schema_version` is present.
- `lifeline.read_only_hardware` is true.
- no repair session is created on a healthy pool.
- no replacement candidate is presented without an active verified drive-repair session.
- the Flight Manual does not advertise a drive replacement when no fault exists.
- normal dashboard polling remains stable.

Expected result: Lifeline is invisible when there is nothing to repair.

## Gate 3: model-specific service profile

Verify the physical chassis is the supported BattleStation model before configuring the Lifeline service profile.

For BattleStation the intended profile is:

```yaml
hardware:
  lifeline:
    service_profile: qnap-tvs-x71
    chassis_model: TVS-671
```

Verify Mission Control reports the source-backed TVS-x71 service profile and does not infer the profile from bay count, hostname, or DMI fragments.

Expected result: the physical-service procedure gate is satisfied only because an exact supported model was explicitly configured.

## Gate 4: deterministic repair session on the live host

Exercise the complete drive-repair state machine with HoloDeck/deterministic evidence while keeping real storage healthy.

The deterministic scenario should prove:

1. a FAULTED member opens a persistent Lifeline session;
2. logical member and physical bay evidence must agree;
3. backup-state acknowledgement advances metadata only;
4. an undersized replacement is rejected;
5. a candidate with existing/preserved data is rejected;
6. a valid candidate can satisfy planning prerequisites;
7. `can_execute_replacement` remains false;
8. resilver telemetry forces `monitor_recovery`;
9. three consecutive healthy observations are required for closure;
10. the completed session survives a service restart.

Expected result: the live host can run the Lifeline software path without any real pool mutation.

## Gate 5: replacement-media discovery

Test read-only candidate discovery with non-pool media only.

Prefer a spare disk or removable test device that is not a member of any TrueNAS pool and contains no data that needs to be preserved.

Verify:

- boot media and internal NVMe devices are excluded;
- active pool members are rejected;
- capacity is reported correctly;
- a too-small candidate is blocked;
- existing filesystem/partition signatures are treated as preserve-data risk;
- failed signature inspection fails closed;
- Linux device-name reuse alone is not accepted as proof of new media;
- a serial change is required for same-path hot-swap identity.

Do not wipe the test disk as part of Lifeline validation.

Expected result: Lifeline can identify suitable media without modifying it.

## Gate 6: physical bay identification

This is the first real hardware-control test in the Lifeline ladder.

Run it only with an operator physically in front of BattleStation.

Prerequisites:

- exact TVS-671 service profile verified;
- Lifeline session identifies a single exact bay;
- current enclosure mapping independently agrees with the session;
- no browser-supplied arbitrary bay value is accepted;
- the target bay is visually known before the command is sent.

Trigger the Lifeline Identify Bay action for the test session.

Verify:

- only the expected physical bay identify LED flashes;
- no adjacent bay changes state;
- no disk activity/state changes;
- the identify LED auto-clears after the bounded interval;
- a second request for an unsupported/ambiguous session is rejected.

Abort immediately if the wrong bay illuminates.

Expected result: Lifeline can bridge a verified logical fault identity to the correct physical bay without exposing generic bay control.

## Gate 7: persistence and restart

With a non-destructive test session active:

1. record the session ID and original-fault identity;
2. restart Mission Control;
3. verify the same session returns;
4. verify acknowledgement state remains intact;
5. verify the original fault identity has not been rewritten by current device enumeration;
6. complete the deterministic recovery sequence and verify the session moves to completed history.

Expected result: repair state survives the exact lifecycle events an operator can encounter during maintenance.

## Gate 8: regression sweep

After Lifeline live tests, verify the rest of TruePanel again:

- LCD rotation and buttons
- Mission Control status and history
- fan telemetry and guarded profiles
- thermal safety state
- network telemetry
- storage health
- compatibility survey
- service restart behavior

Expected result: Lifeline is additive and does not regress existing platform behavior.

## Exit criteria

Project Lifeline is considered live-test ready for review when all of the following are true:

- latest branch CI is green;
- installed-wheel smoke passes;
- healthy BattleStation produces no false repair session;
- exact TVS-671 service-profile provenance is correct;
- deterministic drive-repair session works on the live host;
- replacement discovery remains read-only and fail-closed;
- physical bay identification selects only the verified bay and auto-clears;
- session persistence survives restart;
- no storage-write API or command is reachable through Lifeline;
- existing TruePanel functionality passes a final regression sweep.

Actual pool-member offline/replace execution is a separate future authority project and is not part of this live-test plan.
