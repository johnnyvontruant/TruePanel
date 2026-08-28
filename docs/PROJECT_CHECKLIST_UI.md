# Project CHECKLIST Mission Control UI

Project CHECKLIST is the cockpit presentation layer for TruePanel guided recovery.
It does not replace Health Intelligence, Operator Guidance, or Project Lifeline.

## Data path

1. Health and watcher logic identify a condition.
2. Operator Guidance selects the appropriate Flight Manual procedure and publishes verified evidence.
3. Project Lifeline evaluates evidence-bound repair phases, gates, replacement validation, and recovery verification where a specialized repair engine exists.
4. Project CHECKLIST converts that state into an operator-facing procedure model.
5. Mission Control renders CHECKLIST inside the existing Flight Manual card.

CHECKLIST is additive. It does not create a competing recovery system.

## UI states

CHECKLIST uses explicit state language:

- **MACHINE VERIFIED**: the gate is backed by current telemetry, verified provenance, or an explicit guarded acknowledgement.
- **HOLD**: a required gate is not yet satisfied.
- **BLOCKED**: the step is unavailable by design or lacks required authority.
- **MONITOR**: recovery is already active and additional service must wait.
- **AUTHORITY HOLD**: planning prerequisites are complete, but execution authority is intentionally absent.
- **VERIFIED COMPLETE**: machine verification confirms the recovery is complete.

Human procedure text is never automatically marked complete simply because a recovery phase advanced.

## Interaction contract

The CHECKLIST cockpit can expose expandable procedure sections and may surface existing guarded Lifeline operator checkpoints. It must not add manual PASS, Resolve, or completion controls that can override machine verification.

Existing guarded Lifeline actions remain the authority for metadata acknowledgements and verified bay identification. CHECKLIST does not duplicate those endpoints.

## Storage safety boundary

The current CHECKLIST and Lifeline architecture has no storage-write authority. The Mission Control CHECKLIST surface must not offline, remove, replace, wipe, partition, or force a storage operation.

Destructive procedure text is displayed as authority locked even when it is part of the documented repair sequence.

`can_execute_replacement` remains false in the current architecture.

## Mobile contract

Mission Control mobile usability is a release constraint. CHECKLIST must preserve the existing phone layout rather than behaving as a desktop panel squeezed into a narrow viewport.

At the mobile breakpoint:

- status and header rails stack vertically;
- mission target, phase, and procedure state become one column;
- preflight and capability sections become one column;
- procedure steps remain readable without horizontal scrolling;
- chips wrap instead of forcing the card wider than the viewport;
- existing Flight Manual and Lifeline controls remain reachable.

Desktop improvements must not regress phone usability.

## Aviation vocabulary

The recovery architecture uses the following project language:

- **CHECKLIST**: procedure state and operator presentation.
- **FLIGHT MANUAL**: troubleshooting and repair knowledge.
- **WINGMAN**: operator assistance.
- **VECTOR**: recommendation and routing.
- **CREW CHIEF**: hardware maintenance workflows.
- **PAN-PAN**: serious degraded condition.
- **MAYDAY**: critical immediate-response condition.
