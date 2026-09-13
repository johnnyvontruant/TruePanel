# Workload Awareness

TruePanel should explain not only whether the NAS is healthy, but what useful work it is doing. OBSERVATORY is the normalization boundary for that purpose.

## Workload families

- media playback and transcoding;
- media import and download activity;
- backup and replication tasks;
- scheduled maintenance and scrub activity;
- application jobs and service activity;
- user-defined providers that can emit privacy-safe normalized observations.

## Presentation contract

Pilot mode should answer what the system is busy doing in one short CURRENT ACTIVITY statement. Flight Engineer may show provider, state, progress, intensity, confidence, and timing.

The default contract is privacy preserving: workload titles should be generic unless a provider has an explicit reason to expose content identity. User names, filenames, media titles, credentials, and private paths are not required for the core activity model.

## Cargo Bay

Cargo Bay remains useful, but it should become one workload-oriented view rather than the definition of workload awareness. Recent media arrivals, download progress, and backup-manifest state are Cargo-specific details. OBSERVATORY can place those alongside ZFS operations, backup/replication, maintenance, and application activity without turning Mission Control into a media-manager clone.

## Next implementation slice

1. Define provider-neutral workload categories.
2. Map existing ZFS and Cargo observations into those categories.
3. Add a generic scheduled-job/backup provider using read-only evidence.
4. Keep CURRENT ACTIVITY bounded and consequence-oriented in Pilot.
5. Use Flight Engineer for provider provenance and diagnostics.
