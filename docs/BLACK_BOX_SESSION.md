# Black Box Replay Session

`BlackBoxReplaySession` is the offline integration boundary for Black Box tooling. It composes one validated source replay with an optional simulation-only chaos scenario, the LCD Digital Twin projection, and deterministic incident narration.

The source recording remains immutable. Chaos faults are projected into a separate derived replay. Replacing a chaos scenario always begins again from the original recording, so simulated failures cannot silently stack across browser or support-tool operations.

Every `BlackBoxReplayView` is data-only and contains the sanitized frame, renderable LCD state, and incidents observed at that sequence. Recorder-backed sessions and compatibility-replay seed profiles use the same boundary.

## Safety boundary

The session layer has no serial, sysfs, socket, systemd, fan-control, Host Agent, service-restart, network-fetch, or callback execution path. It cannot actuate hardware or promote simulated evidence into live hardware authority. Compatibility replay continues to avoid inventing LCD or other runtime state that was not present in the support bundle.
