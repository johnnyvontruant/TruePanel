# AEGIS Governed Passive Runtime

This increment turns the passive provider prototype into an activation gate.
It bounds TrueNAS API traffic, verifies the current session's roles, reads
restore receipts only from a governed directory, and fails closed before any
protection query when those controls are absent.

It does not activate a provider in Mission Control by default, create a user or
API key, deploy software, or change TrueNAS configuration.

## Runtime contract

`BoundedTrueNASQueryCache` permits four passive methods: `auth.me`,
`disk.query`, `replication.query`, and `cloud_backup.query`. The default cache
TTL is 60 seconds, stale reuse is bounded to 300 seconds, and at most eight
entries can exist. Repeated Mission Control status frames therefore reuse one
observation instead of creating a polling multiplier.

Stale evidence is display-only. If middleware becomes unavailable after a
successful observation, the operator can still see the last bounded result,
but recovery immediately returns to `HOLD` and the cached receipt cannot clear
CHECKRIDE.

`TrueNASRoleVerifier` calls `auth.me` before protection or inventory methods.
It requires `READONLY_ADMIN`, `REPLICATION_TASK_READ`, and
`CLOUD_BACKUP_READ`, and rejects `FULL_ADMIN`, sharing or replication
administrator roles, every `*_WRITE` or `*_DELETE` role, and filesystem full
control. Account names and API keys are never included in the observation.

`GovernedRestoreReceiptStore` performs no writes. Its directory and receipt
must be owned by the runtime UID, not group/world writable, not symlinks, and
the receipt must be a regular JSON file no larger than 64 KiB. Receipt names
are SHA-256 hashes of incident IDs, preventing caller-controlled paths. The
receipt's incident, task, and dataset scope must all match observed TrueNAS
evidence.

## Why the local root socket does not pass

The default local `midclt` socket inherits the authority of its caller. A root
or `truenas_admin` observation reports `FULL_ADMIN`; AEGIS intentionally marks
that session `HOLD` before reading task data. Read-only method selection is not
a substitute for least-privilege authentication.

TrueNAS 25.10 documents `READONLY_ADMIN` as the minimum role for
`disk.query`; `replication.query` additionally documents
`REPLICATION_TASK_READ`, and `cloud_backup.query` documents
`CLOUD_BACKUP_READ`. TrueNAS also warns that user-linked API keys are
password-equivalent and require secure transport. This increment therefore
does not place an API key on a command line or silently create a credential.
A separately reviewed authenticated client adapter is required before live
activation.

## No-deploy observation

The packaged observer writes only sanitized JSON to standard output:

```console
python -m truepanel.aegis.passive_observation \
  --incident-id 'recovery:INCIDENT_ID' \
  --receipt-root /path/to/reviewed/read-only-receipts
```

Running it through BattleStation's local root socket is expected to produce a
role-gate `HOLD`. That result proves the guard, not a product failure. The
output excludes task paths, task names, account names, secrets, and raw
receipts, and explicitly reports `deployment_changed: false` and
`control_authority: false`.

## Deterministic proof

The HoloDeck rehearsal makes three middleware calls on the first observation
and zero additional calls on the second, a 100% reduction for the repeated
frame. Four adversarial paths all hold: full administrator authority, mutable
receipt storage, stale cached evidence, and a restore-scope mismatch. There are
zero unsafe false-ready results, zero mutating calls, and zero runtime receipt
writes.

Reproduce with:

```console
pytest -q tests/test_aegis_passive_runtime.py tests/test_aegis_passive_runtime_rehearsal.py
python -c "from truepanel.holodeck.aegis_passive_runtime import run_passive_runtime_rehearsal as run; print(run()['measurements'])"
```

## Prior art and provenance

- [TrueNAS 25.10 RBAC](https://api.truenas.com/v25.10/rbac.html) defines role
  expansion, write-role inclusion, and `auth.me` inspection.
- [TrueNAS `auth.me`](https://api.truenas.com/v25.10/api_methods_auth.me.html)
  returns the active session and its privilege information.
- [TrueNAS API access guidance](https://www.truenas.com/docs/scale/api/)
  documents user-linked API keys, revocation, expiration, and secure-transport
  requirements.
- [TrueNAS API client](https://github.com/truenas/api_client) supplies `midclt`
  and its local/remote connection semantics.

The implementation is original TruePanel code. No TrueNAS source, credential,
runtime dependency, or third-party binary was incorporated.

## Failed and deferred paths

- Trusting a root local socket because every selected method is read-only:
  rejected; the session still holds unrestricted authority.
- Serving stale cached evidence as recovery proof: rejected; stale data is
  visibility-only and forces HOLD.
- Accepting a valid receipt whose dataset scope differs from its task:
  rejected by an explicit scope match.
- Passing an API key to `midclt -K`: deferred because command-line arguments
  can expose credentials to process inspection.
- Automatically provisioning a TrueNAS service account or privilege: deferred
  because it is a security/configuration change outside this read-only slice.

That client boundary is now implemented and rehearsed in
[`AEGIS_CREDENTIAL_SAFE_SESSION.md`](AEGIS_CREDENTIAL_SAFE_SESSION.md). The
remaining gate is an operator-created expiring least-privilege account and one
no-deploy BattleStation observation through a trusted TLS hostname, followed by
review of the sanitized result.
