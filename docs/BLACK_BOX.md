# TruePanel Black Box

Black Box is an experimental, read-only record/replay foundation for support and simulation. It captures already-collected TruePanel state into compact JSONL frames. The first implementation is deliberately not wired into the runtime and performs no hardware I/O.

## Privacy contract

Every frame is sanitized before storage. Sensitive mapping keys such as host names, IP/MAC addresses, drive serials, WWNs, UUIDs, usernames, tokens, passwords, and filesystem paths are replaced with `<redacted>`. IP, MAC, and UUID literals embedded inside arbitrary strings are scrubbed as well, including LCD lines and alert messages.

A replay refuses frames that are not explicitly marked `privacy: sanitized` or that use an unsupported schema version. This keeps exported recordings fail-closed instead of silently accepting unknown/raw formats.

## Frame contents

Schema version 1 reserves compact sections for telemetry, LCD state, fan state, storage state, alerts, button state, and Mission Control state. `BlackBoxFrame.capture()` accepts plain mappings so later runtime integration can remain decoupled from hardware providers.

`BlackBoxRecorder` appends one deterministic compact JSON object per line and enforces a per-frame size ceiling. Replay is sequential and raises a line-numbered error for malformed or unsafe frames.

## Safety boundary

Black Box is data plumbing only. It does not start services, call hardware providers, actuate fans or LEDs, open the A125 transport, or modify the live deployment. Later integration should preserve that observer-only boundary.
