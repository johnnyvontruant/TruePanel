# Black Box Replay API Contract

`BlackBoxReplayAPI` is a transport-neutral, read-only contract over `BlackBoxReplaySession`. It prepares bounded dictionaries that a future Mission Control replay UI can serialize without coupling the replay engine to an HTTP server or live TruePanel runtime.

The contract exposes recording metadata, exact sequence lookup, timestamp seeking, bounded timeline windows, incident history, and the set of supported simulation-only chaos fault kinds. Scenario requests are validated against a small allowlist and bounded fault count before any future projection layer may consume them.

## Safety boundary

This module is deliberately not a web server. It opens no sockets, imports no hardware providers, runs no callbacks, changes no services, writes no recording data, and has no fan, serial, sysfs, Host Agent, upgrade, or deployment authority. All response payloads are marked `read_only`, and chaos metadata is marked `simulation_only`.

A later Mission Control adapter may map these data-only methods to HTTP routes, but that adapter must retain the same offline separation: replay input is previously sanitized Black Box data, not a bridge back into the live NAS.
