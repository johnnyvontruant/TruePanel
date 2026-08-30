# Flight Director Prior-Art Field Report

Reviewed 2026-08-30. This pass inspected current official product documentation and
upstream project documentation. No third-party source, binary, model, dataset,
credential, or notice-bearing artifact was incorporated.

## NAS patterns

| Project | Useful capability | Decision for TruePanel |
| --- | --- | --- |
| Synology Active Insight | Historical performance, anomaly warnings, risk indicators, troubleshooting advice, and mobile monitoring | Adapt the early-warning-to-advice journey, but keep TruePanel local-first and evidence-visible instead of requiring a cloud fleet service. |
| QNAP DA Drive Analyzer | Large-population drive prediction and explicit drive compatibility limits | Preserve compatibility and calibration limits; defer the licensed/cloud prediction service because it is opaque and cannot be replayed locally. |
| QNAP Security Center | Risk-oriented findings and guided action | Adapt the separation between finding, risk, and recommendation; do not combine it with hardware control. |
| TrueNAS Drive Health | Affected-disk identity, alert detail, and recommended next steps | Reuse the host's passive facts through Lifeline; never duplicate SMART scheduling or mutate TrueNAS tasks. |
| Unraid | Real-time notifications, broad community applications, and an open API | Learn from extensibility and event delivery; avoid plugin sprawl inside the reliability core. |
| openmediavault | Simple smartmontools integration and service notifications | Treat it as evidence that collection can stay thin; TruePanel's advantage is cross-signal replay and verified recovery. |
| ASUSTOR ADM | Accessible activity and health surfaces | UI inspiration only; official material did not expose a reusable causal or verification engine. |

## Adjacent patterns

- OpenTelemetry context propagation connects signals through shared causal context.
  Flight Director adapts that semantic idea with explicit graph edges and certainty;
  no OpenTelemetry runtime dependency was added.
- MLflow records parameters, metrics, artifacts, runs, and lineage. HANGAR adapts the
  durable run-and-artifact memory, but a server/database dependency would be excessive
  for a repository-sized experiment program.
- Backstage TechDocs keeps documentation beside code and indexes it centrally. HANGAR
  follows the same source-of-truth principle: existing manuals stay put while the
  registry supplies generated views.
- DVC-style content addressing and dataset-card concepts already inform AEGIS evidence
  governance. HANGAR verifies byte-level artifact hashes with the standard library.

## Build versus adopt

Build the small TruePanel-owned registry, causal map, linear fixture forecast, and
repair signature. They are domain-specific, dependency-light, replaceable, and tested.
Adopt only semantics from the systems above. A cloud health service, general ML
tracking server, generic graph database, or auto-remediation runner would add privacy,
security, and operational weight before TruePanel has representative field evidence.

## License and provenance

This increment contains original MIT-licensed TruePanel code. Product documentation
supplied factual and interaction patterns only. No vendor code was copied. OpenTelemetry
(Apache-2.0), MLflow (Apache-2.0), Backstage (Apache-2.0), and DVC (Apache-2.0) remain
potentially compatible reference projects; none is a runtime or source dependency here.

## Rejected or deferred routes

- Exact fan/bay/pool inference from aggregate telemetry: rejected as unsafe fiction.
- Cloud prediction as a prerequisite: rejected for privacy, availability, and replayability.
- General graph database: deferred; 13 deterministic nodes do not justify a service.
- Probabilistic forecasting library: deferred until field data can calibrate it.
- Automatic repair: rejected; Flight Director remains advisory with control authority false.

Most promising collaboration: Scrutiny and smartmontools maintainers for portable SMART
evidence semantics, paired with TrueNAS enclosure/topology maintainers for passive,
identity-safe bay and pool mapping.

## Sources

- https://www.synology.com/en-global/dsm/feature/active-insight/overview
- https://www.qnap.com/en-us/how-to/faq/article/why-do-predictions-from-ulink-da-drive-analyzer-sometimes-differ-from-s-m-a-r-t-warnings
- https://www.qnap.com/en-us/how-to/faq/article/da-drive-analyzer-support-drives
- https://www.truenas.com/docs/scale/storage/disks/drivehealthmanagement/
- https://docs.unraid.net/API/upcoming-features/
- https://docs.openmediavault.org/en/8.x/administration/storage/smart.html
- https://www.asustor.com/online/online_help?id=11
- https://opentelemetry.io/docs/concepts/context-propagation/
- https://mlflow.org/docs/latest/ml/tracking/
- https://backstage.io/docs/features/techdocs/addons/

