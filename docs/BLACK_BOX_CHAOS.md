# Black Box Chaos Simulation

The experimental Black Box chaos layer injects deterministic failures into recorded `BlackBoxFrame` data only. It exists for replay tests, Digital Twin development, support reproduction, and future release-candidate exercises without touching a live TruePanel runtime.

Supported faults are deliberately small and explicit: `fan_stall`, `storage_degraded`, `lcd_stale`, and `mission_control_unavailable`. Each overlay marks the affected projection with `simulated_fault` and appends a sanitized warning alert with `simulated: true`.

`inject_chaos_fault()` returns a new sanitized frame and never mutates the recording. `BlackBoxChaosScenario` maps exact recorded sequence numbers to bounded fault overlays so tests can replay the same failure at the same point every time.

## Safety boundary

This module does not import hardware drivers, serial transports, command sockets, systemd helpers, sysfs providers, fan-control code, or live Mission Control providers. It cannot request a fan profile, alter a pool, restart a service, activate the Host Agent, or send an A125 command. Unknown fault names fail closed instead of providing a generic command or callback escape hatch.

Fault detail metadata is passed back through the Black Box privacy sanitizer before it enters a simulated alert. This preserves the privacy-safe recording contract even when test scenarios contain hostnames, addresses, or other identifying values.
