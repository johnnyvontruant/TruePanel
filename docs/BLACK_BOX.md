# TruePanel Black Box

Black Box is an experimental, read-only record/replay foundation for support and simulation. It captures already-collected TruePanel state into compact JSONL frames. The implementation is deliberately not wired into the runtime and performs no hardware I/O.

## Privacy contract

Every frame is sanitized before storage. Sensitive mapping keys such as host names, IP/MAC addresses, drive serials, WWNs, UUIDs, usernames, tokens, passwords, and filesystem paths are replaced with `<redacted>`. IP, MAC, and UUID literals embedded inside arbitrary strings are scrubbed as well, including LCD lines and alert messages.

A replay refuses frames that are not explicitly marked `privacy: sanitized` or that use an unsupported schema version. This keeps exported recordings fail-closed instead of silently accepting unknown/raw formats.

## Frame contents

Schema version 1 reserves compact sections for telemetry, LCD state, fan state, storage state, alerts, button state, and Mission Control state. `BlackBoxFrame.capture()` accepts plain mappings so later runtime integration can remain decoupled from hardware providers.

`BlackBoxRecorder` appends one deterministic compact JSON object per line and enforces a per-frame size ceiling. Sequential replay raises a line-numbered error for malformed or unsafe frames.

## Deterministic replay

`BlackBoxRecorder.load_replay()` loads a recording into `BlackBoxReplay`. A replay requires strictly increasing sequence numbers and timestamps that never move backward, rejecting ambiguous recordings before a simulator or UI can consume them.

Replay is intentionally wall-clock free. Consumers can query an exact sequence, find the latest frame at or before a timestamp, select an inclusive time window, or create a `BlackBoxReplayCursor` for deterministic stepping and seeking. The cursor clamps ordinary step operations to the recording bounds and never calls runtime providers or hardware.

These primitives are intended to become the common substrate for replay fixtures, a browser-based Digital Twin, and later simulation/incident-analysis tooling without giving those consumers access to live hardware paths.

## Safety boundary

Black Box is data plumbing only. It does not start services, call hardware providers, actuate fans or LEDs, open the A125 transport, or modify the live deployment. Later integration should preserve that observer-only boundary.
