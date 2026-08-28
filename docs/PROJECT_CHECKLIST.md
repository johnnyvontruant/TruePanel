# Project CHECKLIST

Project CHECKLIST is TruePanel's cockpit procedure layer for guided recovery.
It turns active operator guidance into ordered, evidence-bound procedures that
Mission Control can present without granting the presentation layer hardware or
storage authority.

## Architecture

The recovery stack deliberately separates responsibilities:

1. Watchers and Health Intelligence detect observable faults.
2. Operator Guidance selects the relevant procedure and supporting evidence.
3. Project Lifeline evaluates drive-repair phases, prerequisites, replacement
   candidates, acknowledgements, and recovery state.
4. Project CHECKLIST presents those facts as cockpit-style procedure state.
5. Any future write-capable authority remains a separate guarded subsystem.

CHECKLIST does not duplicate Lifeline's repair evaluator. For drive recovery it
uses Lifeline's gates as the source of truth for preflight status.

## Status snapshot contract

`augment_status_snapshot()` publishes an additive `operator_checklists` list.
Each active guidance card receives one checklist payload.

A checklist contains:

- fault code, title, severity, and current phase;
- target and evidence already established by guidance/Lifeline;
- Lifeline-backed preflight gates when a repair session exists;
- ordered immediate-action, diagnosis, remediation, and verification steps;
- warnings and blockers;
- read-only capability flags such as bay-identification readiness;
- explicit `read_only: true` state.

Human procedure text is never marked complete merely because the workflow has
advanced. Only Lifeline gates backed by observed evidence or explicit operator
acknowledgements can appear as verified.

## Mission Control presentation

CHECKLIST renders inside the existing Flight Manual guidance cards rather than
creating a competing recovery panel. The cockpit surface shows current phase,
target identity, procedure state, machine-verified preflight gates, capability
locks, warnings, and expandable recovery sections.

Generic fault procedures expose only generic authority such as safe diagnostics
and disruptive-action locks. Storage-specific capability rows such as bay
identification and replacement readiness appear only for faulted-drive recovery.

Existing guarded Lifeline actions remain responsible for verified bay
identification and backup-state acknowledgement. CHECKLIST does not duplicate
those controls or their confirmation boundaries.

## Storage safety floor

Project CHECKLIST has no authority to offline, remove, replace, wipe, partition,
or otherwise mutate storage. Even when every write prerequisite is satisfied,
Lifeline reports `can_execute_replacement: false` in the current architecture.
CHECKLIST exposes that boundary as an `authority_hold` rather than silently
turning preparation into execution authority.

A resilvering drive-repair session enters a monitor state and must not direct
the operator to service another member.

## Aviation vocabulary

The broader recovery vocabulary is reserved for distinct responsibilities:

- **CHECKLIST**: ordered recovery procedure presentation;
- **FLIGHT MANUAL**: explanatory troubleshooting and service knowledge;
- **WINGMAN**: operator-assistance experience;
- **VECTOR**: recommendation and routing logic;
- **CREW CHIEF**: hardware-maintenance workflows;
- **PAN-PAN**: serious degraded conditions that require attention;
- **MAYDAY**: critical conditions requiring immediate protective response.

These names should describe actual system behavior rather than act as decorative
labels.

## Initial vertical slice

The first CHECKLIST vertical slice covers:

- faulted-drive recovery through existing Lifeline repair sessions;
- verified/hold preflight presentation;
- bay-identification readiness;
- replacement and acknowledgement gates;
- resilver monitoring;
- explicit write-authority separation;
- generic pending procedures for non-storage guidance such as network faults;
- responsive Mission Control cockpit rendering inside the Flight Manual.

Future work may add richer guarded workflow controls, recovery history,
rehearsal against HoloDeck, and additional fault-specific state evaluators.
None of those additions may weaken the storage safety boundary described above.
