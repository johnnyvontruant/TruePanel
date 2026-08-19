# Black Box Compatibility Replay

Compatibility Replay turns an exported, privacy-safe TruePanel compatibility support bundle into a deterministic simulation profile. It is intended for support reproduction, Digital Twin development, replay fixtures, and future compatibility work on machines that are not physically available to the developer.

The replay loader accepts support-bundle schema version 1 only. It requires the complete privacy manifest, rejects unknown schema fields, rejects payloads that would require additional Black Box redaction, and bounds JSON input to 1 MiB by default. A profile preserves the passive classification, installation mode, hardware-control state, and individual compatibility checks exactly as observations rather than inferring capabilities that the survey did not prove.

`CompatibilityReplayProfile.to_black_box_frame()` can create a synthetic Black Box seed frame for downstream replay tools. The seed contains the validated compatibility profile and a simulation-only Mission Control marker. It deliberately does not invent LCD contents, fan telemetry, storage state, alerts, or button activity.

## Safety boundary

Compatibility Replay consumes previously exported JSON only. It does not import or call compatibility discovery, hardware drivers, serial transports, command sockets, sysfs providers, fan-control code, systemd helpers, or live Mission Control providers. Loading or replaying a profile cannot probe a NAS, activate the Host Agent, send an A125 command, request a fan profile, modify a pool, or restart a service.

The support bundle remains evidence, not authority. A replayed `SUPPORTED` classification does not authorize hardware control, and simulated observations must never be promoted into live capabilities without a separate live compatibility and commissioning process.
