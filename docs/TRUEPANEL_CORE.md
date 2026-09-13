# TruePanel Core and Hardware Modules

## Purpose

TruePanel's diagnostic and recovery intelligence should remain useful even when the host has no verified QNAP front panel, bay LED controller, or fan-control path. The product boundary is:

- **TruePanel Core**: normalized evidence, Health Intelligence, ORACLE, AEGIS, Pathfinder, Lifeline semantics, OBSERVATORY, history, Mission Control, HoloDeck, and Black Box.
- **Hardware Modules**: model-specific LCD, LED, fan, buzzer, enclosure, and other actuator/provider integrations that require independent verification.

This is an architectural boundary, not permission to generalize hardware writes.

## First-class no-hardware mode

A host with no verified hardware module should be a supported operating mode, not an error condition. Core services may report hardware capabilities as unavailable while continuing to provide trustworthy generic Linux, SMART, ZFS, service, workload, history, incident-correlation, and recovery evidence.

Absence of a hardware module must never be rendered as a healthy hardware state. It is **not available**, with the reason and missing capability made explicit.

## Capability contract

Core consumes normalized records and capability declarations. Hardware modules may add evidence or actuation only through explicit interfaces. A module declares observation capability, verification evidence, write capability, commissioning state, and control authority separately.

Observation capability never implies write authority. A portable collector may be enabled broadly; an actuator remains model-scoped until independently commissioned.

## Migration path

1. Inventory imports in Core-facing modules and identify QNAP-specific dependencies.
2. Introduce a capability/provider boundary where Core currently constructs hardware directly.
3. Add deterministic fixtures for a generic Linux/ZFS/SMART host with no front panel.
4. Require Mission Control and recovery layers to render that fixture without exceptions, fake green states, or hardware-control affordances.
5. Keep the TVS-671 implementation as the reference hardware module.
6. Only after the single-host portable contract is stable, explore remote agents or fleet aggregation.

## Acceptance criteria

A no-hardware fixture is successful when it can produce a read-only Mission Control snapshot, detect and explain supported generic faults, preserve UNKNOWN/UNAVAILABLE for unavailable evidence, run HoloDeck recovery rehearsals, expose no LCD/LED/fan/storage-mutation authority, and pass the same privacy/provenance rules as the reference platform.

The reference BattleStation remains the hardware-integration proving ground; portable Core work must not weaken its verified guards.
