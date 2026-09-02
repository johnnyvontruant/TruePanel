# AEGIS Passive TrueNAS Evidence Providers

This experiment turns the ground-truth interface from PR #110 into replaceable
read-only adapters for documented TrueNAS 25.10 query methods. It does not
enable live collection by default, create an API credential, or grant repair
authority.

## Contract

`TrueNASReadOnlyQueryClient` permits exactly `disk.query`,
`replication.query`, and `cloud_backup.query`. Every other method, including
`disk.wipe`, is rejected before a subprocess can start. Queries use the local
middleware CLI, a ten-second timeout, JSON-only results, and no passwords.

`TrueNASReplacementInventoryProvider` requires agreement between the existing
Linux/enclosure/signature provider and `disk.query` identity, capacity, and
pool membership. A candidate disappears rather than degrades to a guess when
serial, capacity, identifier, pool state, or preserved-data disposition cannot
be proven.

`TrueNASProtectionEvidenceProvider` records successful replication and cloud
backup tasks as protection coverage. It deliberately does **not** call that a
tested restore. Promotion requires a separate incident-bound verification
receipt with a matching successful task, non-empty scope and test identity,
positive object count, read-only authority, and an intact SHA-256 digest.

## Prior art and provenance

- [TrueNAS `disk.query`](https://api.truenas.com/v25.10.0/api_events_disk.query.html)
  supplies stable identifiers, serials, byte capacity, enclosure information,
  and optional pool joins under a read-only administrator role.
- [TrueNAS replication tasks](https://api.truenas.com/v25.10/api_methods_replication.query.html)
  expose enabled and task-state evidence; write roles are separately required
  for run and restore operations.
- [TrueNAS cloud backup](https://api.truenas.com/v25.10/api_methods_cloud_backup.query.html)
  exposes task/job state, while restore is a distinct write-authorized job.
- [TrueNAS replication UI guidance](https://www.truenas.com/docs/scale/25.10/scaleuireference/dataprotection/replicationscreensscale/)
  labels completed transfer state separately from its explicit restore flow.

The actual TrueNAS middleware implementation and LGPLv3 license were inspected.
TruePanel adapts public API semantics only; it copies no source code and adds no
third-party dependency or credential.

## Deterministic result

The positive HoloDeck fixture accepts both required statements. Three
adversarial paths—successful task without restore proof, candidate already in a
pool, and disk identity mismatch—produce three HOLD decisions and zero unsafe
false-ready outcomes. No mutating method is exercised.

Reproduce with:

```console
pytest -q tests/test_aegis_passive_providers.py tests/test_aegis_passive_provider_rehearsal.py
python -c "from truepanel.holodeck.aegis_passive_providers import run_passive_provider_rehearsal as run; print(run()['measurements'])"
```

## Failed and deferred paths

- Replication `SUCCESS` as restore proof: rejected; transfer completion does
  not demonstrate usable recovery.
- `disk.query` pool absence as proof of blank media: rejected; TruePanel also
  requires local read-only signature evidence.
- Automatic live provider wiring: deferred until query cadence, supported
  least-privilege access, and a governed receipt store are reviewed.
- TrueNAS restore/run calls: prohibited; they are write-authorized jobs.

The strongest follow-up is a bounded, cached provider runtime using an explicit
read-only TrueNAS role and a reviewed local receipt directory, followed by a
passive BattleStation observation that is incapable of changing service or
storage state.

That follow-up is now implemented and rehearsed in
[`AEGIS_GOVERNED_PASSIVE_RUNTIME.md`](AEGIS_GOVERNED_PASSIVE_RUNTIME.md). Live
The credential-safe session is now implemented and rehearsed in
[`AEGIS_CREDENTIAL_SAFE_SESSION.md`](AEGIS_CREDENTIAL_SAFE_SESSION.md). The
local root socket remains deliberately rejected as over-privileged; field
activation still requires operator-controlled least-privilege credentials and
trusted TLS.
