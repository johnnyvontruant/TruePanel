# Black Box Mission Control Replay Adapter

`BlackBoxMissionControlReplayAdapter` is a thin, transport-neutral bridge between the offline `BlackBoxReplayAPI` contract and a future Mission Control Digital Twin UI. It maps route-shaped GET requests to bounded dictionaries without attaching any route to TruePanel's live web server.

The adapter currently exposes metadata, exact frame lookup, timestamp seeking, bounded timeline windows, incident history, and simulation-only chaos capability discovery under the `/api/v1/replay` namespace. It returns explicit HTTP-like status codes for malformed input, missing frames, unknown routes, and non-read-only methods, but it does not open a network listener.

## Safety boundary

This module is offline-only. It imports the Black Box replay API and standard-library URL parsing, but no live Mission Control server/service module, hardware provider, Host Agent path, serial transport, subprocess helper, or socket layer. It cannot restart services, mutate a replay session, apply chaos faults, issue fan/storage commands, or reach the NAS.

This separation is intentional. A later browser adapter may serialize `ReplayRouteResponse` objects, but live route registration must remain a separate, explicit integration step with its own safety review.
