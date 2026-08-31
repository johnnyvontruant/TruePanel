# TruePanel 1.3.0 Release Notes

TruePanel 1.3.0 moves the platform from health visibility into evidence-backed guided recovery and predictive reliability while preserving conservative hardware and storage authority boundaries.

## Highlights

- Project Pathfinder adds durable guided-recovery sessions, operator workflow state, machine-verification gates, and recovery timelines.
- Project Lifeline adds fail-closed recovery guidance for replacement-worthy SMART evidence joined to verified storage identity.
- Project ORACLE adds adaptive baselines, developing-fault analysis, cross-signal correlation, and deterministic HoloDeck scenarios.
- Project AEGIS adds read-only probable-cause correlation, a universal Recovery Coverage Matrix, request-independent predictive sampling, verification rehearsals, Black Box evidence capture, and mobile-first reliability presentation.
- Project HANGAR preserves experiment dossiers and CI-enforced evidence for completed, failed, active, and future investigations.
- Flight Director adds incident timeline, causal hardware mapping, operating-envelope forecasts, deterministic what-if rehearsal, and repair-verification signatures.
- GLASS COCKPIT reorganizes Mission Control around operator decisions with a persistent Now / Why / Safest Move / Proof command strip and responsive mobile behavior.
- Supported TrueNAS POSTINIT persistence now restores `i2c-dev` across reboot through the middleware-managed Init/Shutdown Scripts contract.
- Drive-temperature telemetry is localized to verified physical bays before the final Pathfinder/AEGIS status composition, so the hottest-drive reliability evidence can report the physical bay when topology is known and explicitly preserve uncertainty when it is not.

## Safety boundaries

- Pathfinder, Lifeline, ORACLE, and AEGIS do not gain destructive storage authority.
- AEGIS remains read-only and cannot hide or delete contributing alerts.
- ORACLE statistical drift cannot invent a production hard fault.
- Flight Director and HANGAR remain evidence, correlation, and rehearsal surfaces without hardware or service-control authority.
- SMART recovery remains fail-closed until the required evidence and verification gates are satisfied.
- Physical-bay localization reuses verified topology evidence and never guesses an unresolved bay.

## Reference-platform validation

The post-1.2 stack has been deployed and live-validated on the reference QNAP TVS-671 running TrueNAS SCALE 25.10.5. Validation includes Mission Control, the physical LCD and buttons, supported `i2c-dev` reboot persistence, HANGAR evidence loading, AEGIS recovery coverage, and a genuine critical-SMART incident that exercised the guided-recovery stack.

The 1.3.0 release-prep branch adds an end-to-end regression proving that Pathfinder localizes drive-temperature readings before AEGIS observes the final `/api/v1/status` payload.

## Release gate

Before tagging `v1.3.0`:

1. Merge the 1.3.0 release-prep pull request only after authoritative GitHub Actions is fully green, including the installed-wheel smoke job.
2. Confirm `pyproject.toml` and `truepanel.__version__` both report `1.3.0`.
3. Run the guarded deployment lifecycle on BattleStation: stage, validate, promote, and retain the rollback generation.
4. Confirm both TruePanel services are active and Mission Control `/healthz` is healthy.
5. Confirm `/api/v1/status` reports physical-bay localization for known drive-temperature evidence and preserves `bay: null` when topology is unresolved.
6. Run `truepanel verify` and the applicable Host acceptance checks.
7. Tag the exact validated merge commit as `v1.3.0` and publish these notes with the release.

## Upgrade

Use the documented guarded upgrade workflow in `docs/UPGRADING.md`. Do not replace the deployed tree manually or bypass verification/rollback protection.
