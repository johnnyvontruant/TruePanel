# Black Box Digital Twin

The experimental Digital Twin is a read-only projection layer over validated Black Box recordings. It turns recorded LCD payloads into deterministic fixed-width display state without consulting live providers or opening hardware devices.

`project_lcd_state()` converts one sanitized `BlackBoxFrame` into an immutable `DigitalTwinLCDState`. Lines are padded or truncated to the requested LCD width, with 16 columns as the default. Missing LCD payloads render as an explicit unavailable state rather than reaching into runtime state.

`BlackBoxDigitalTwin` projects an entire `BlackBoxReplay` and preserves the replay model's exact sequence/time queries. Consumers can request the LCD state for a sequence, the latest state at or before a timestamp, an inclusive time window, or the full projected timeline.

This module intentionally contains no browser server, serial access, command socket calls, hardware actuation, service control, or live Mission Control integration. Those boundaries keep recordings safe to inspect in tests and future support tooling before any UI wiring is considered.
