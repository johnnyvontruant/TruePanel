# AEGIS credential-safe passive WebSocket adapter

Status: review candidate. No deployment or BattleStation configuration change is performed by this branch.

## Purpose

The governed passive runtime cannot use the local root middleware socket because `auth.me` correctly exposes `FULL_ADMIN`, which the AEGIS role gate rejects. This adapter provides a separate authenticated JSON-RPC 2.0 WebSocket transport for an operator-created, expiring, read-only TrueNAS service account while preserving the existing passive method allowlist and fail-closed runtime.

## Transport contract

The adapter:

- requires `wss://` and TLS certificate verification;
- accepts only the `/api/current` endpoint;
- rejects credentials embedded in the URI;
- lazily imports the TrueNAS-provided `truenas_api_client`, so TruePanel gains no new package dependency;
- authenticates with `auth.login_ex` using `API_KEY_PLAIN` and `login_options.user_info=false`;
- holds one persistent authenticated WebSocket session for the observation process;
- exposes only `auth.me`, `disk.query`, `replication.query`, and `cloud_backup.query` to AEGIS;
- performs no write, delete, restore, wipe, replace, offline, service, privilege, user, or API-key mutation.

The adapter does not decide whether the session is safe. Immediately after authentication, the existing governed runtime calls `auth.me`. The runtime continues only when the expanded active roles contain the required read roles and no forbidden administrative, write, delete, or full-control role.

## Credential boundary

The API key itself is never accepted as a command-line argument and is never included in observation output.

The key must be supplied through a local file that:

- is a real regular file, not a symlink;
- is owned by the runtime UID;
- grants no group or world permissions;
- is non-empty and no larger than 4096 bytes.

The observer publishes only the credential governance status. It does not publish the key, key-file path, username, or WebSocket host.

For a root-run no-deploy observation, a suitable temporary key file can be created with owner-only permissions and removed immediately after the observation. TruePanel does not create, rotate, persist, or delete the TrueNAS API key itself.

## Operator prerequisite

The operator must create the TrueNAS account and expiring user-linked API key outside TruePanel. The account must satisfy the runtime's current role contract:

- required: `READONLY_ADMIN`, `REPLICATION_TASK_READ`, `CLOUD_BACKUP_READ`;
- forbidden: `FULL_ADMIN`, `SHARING_ADMIN`, `REPLICATION_ADMIN`, any role ending in `_WRITE` or `_DELETE`, and `FILESYSTEM_FULL_CONTROL`.

`auth.me` is authoritative. A UI label, intended privilege, or account name cannot bypass the runtime check.

## No-deploy observation

The packaged observer keeps the existing local-socket mode. WebSocket mode is selected only when all three transport arguments are supplied:

```bash
python -m truepanel.aegis.passive_observation \
  --incident-id INCIDENT_ID \
  --receipt-root /path/to/governed/receipts \
  --websocket-uri wss://truenas.example/api/current \
  --username truepanel-aegis \
  --api-key-file /root/.config/truepanel/aegis-api-key
```

The command line contains the username, URI, and key-file path, but never the API key value.

The observation remains stdout-only and reports:

- runtime HOLD/READY state;
- sanitized role-gate result;
- governed receipt-store state;
- cache source, age, and call counters;
- transport TLS/authentication and credential-governance state;
- `read_only=true`;
- `control_authority=false`;
- `deployment_changed=false`.

It deliberately omits task bodies, account identity, host identity, credential material, and receipt contents.

## Failure semantics

Any of the following results in HOLD or transport unavailability:

- insecure `ws://` transport;
- wrong WebSocket endpoint;
- URI-embedded credentials;
- missing, symlinked, over-permissive, oversized, malformed, or wrong-owner key file;
- failed authentication;
- unavailable `auth.me`;
- missing required read roles;
- any forbidden role;
- insecure receipt storage;
- stale evidence;
- invalid or scope-mismatched restore receipt.

A failed authentication attempt is not retried repeatedly within one adapter instance. A new observer process is required for another attempt.

## Live boundary

This branch can prove the transport contract and sanitation properties in CI, but it cannot manufacture a BattleStation observation. Completion requires one operator-authorized run against an expiring least-privilege account on BattleStation. The resulting JSON must be reviewed for sanitation before it is retained as field evidence or used to advance HANGAR state.

## References

- TrueNAS 25.10 JSON-RPC 2.0 over WebSocket API
- TrueNAS 25.10 `auth.login_ex`
- TrueNAS 25.10 `auth.me`
- TrueNAS 25.10 role-based access control
- TrueNAS API-key security guidance
