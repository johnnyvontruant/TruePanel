# TruePanel Documentation

This directory is the operating manual for the current TruePanel platform.

## Start here

- [Mission Control and reliability](MISSION_CONTROL.md) for the cockpit, Preflight, Health Intelligence, Pathfinder, Lifeline, ORACLE, AEGIS, mobile behavior, and access boundaries
- [Installation](INSTALLATION.md) for compatibility checks, native deployment, service activation, configuration, and removal
- [Upgrade and rollback](UPGRADING.md) for guarded staging, promotion, verification, cleanup, repair, and recovery
- [CLI reference](CLI.md) for diagnostics, lifecycle, simulation, plugins, hardware, and laboratory commands
- [Hardware support](HARDWARE.md) for verified controllers, ports, command maps, and safety boundaries

## Operations and recovery

- [Clean-install validation](CLEAN_INSTALL_VALIDATION.md)
- [Clean-install Run 3 results](CLEAN_INSTALL_RUN3_RESULTS.md)
- [Historical telemetry](HISTORICAL_TELEMETRY.md)
- [Project AEGIS](PROJECT_AEGIS.md) for the accepted correlation layer, Recovery Coverage Matrix, experiment evidence, and remaining deployment gates
- [Project HoloDeck](HOLODECK.md) for the hardware-isolated Digital Twin, fault injection, Black Box replay, invariant checks, and Incident Compiler

Project Pathfinder and Lifeline are documented in the [Mission Control guide](MISSION_CONTROL.md) because their primary contract is operator-facing guided recovery.

## Platform design

- [Architecture](ARCHITECTURE.md)
- [Philosophy](PHILOSOPHY.md)
- [Plugin API](PLUGIN_API.md)
- [Roadmap](ROADMAP.md)

## Front-panel and hardware research

- [Project Stargate](STARGATE.md)
- [A125 protocol](A125_PROTOCOL.md)
- [Discovery record](STARGATE_DISCOVERIES.md)
- [Stargate development tools](../development/tools/README.md)

## Project stewardship

- [Development guide](DEVELOPMENT.md)
- [Project history](HISTORY.md)
- [Release process](RELEASE.md)
- [Changelog](../CHANGELOG.md)
- [Security policy](../SECURITY.md)
- [Contributing](../CONTRIBUTING.md)
- [Code of conduct](../CODE_OF_CONDUCT.md)

## Documentation contract

User-visible work is not complete until the relevant documentation is updated.

Documentation must:

- distinguish stable, development, experimental, and hardware-commissioning state;
- preserve read-only and control-authority boundaries;
- provide an actionable recovery path for detected faults;
- state what evidence remains unproven;
- keep installation, upgrade, rollback, and uninstall procedures consistent;
- preserve phone usability as an explicit Mission Control constraint;
- retain license and provenance information for adopted external work.

Git history is the archive for retired implementations. The current tree is intentionally limited to production code, tests, durable documentation, and reproducible laboratory source.
