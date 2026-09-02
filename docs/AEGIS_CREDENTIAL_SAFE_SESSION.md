# AEGIS credential-safe TrueNAS session

Status: deterministic lab proof; not deployed or field validated  
Safety class: read-only evidence; no control authority  
Target platform contract: TrueNAS SCALE 25.10.5 JSON-RPC 2.0 API

## Purpose

This increment closes the credential transport gap left by the governed
passive runtime. It supplies a persistent, authenticated TrueNAS API client
that can query AEGIS's four passive methods without placing an API key in a
command argument, environment variable, log, status payload, or evidence
artifact.

It does not create an account, privilege, API key, certificate, service,
listener, or configuration. Those remain explicit operator-controlled TrueNAS
WebUI steps.

## Security contract

| Boundary | Required behavior |
| --- | --- |
| Transport | Exactly `wss://HOST[:PORT]/api/current`; plaintext `ws://`, URL credentials, queries, fragments, and legacy endpoints are rejected. |
| TLS | Certificate verification is always enabled. There is no insecure switch or automatic downgrade. |
| Credential | Absolute, owner-matching, regular, non-symlink file; no group/world permissions; 1–4096 bytes. |
| Authentication | TrueNAS 25.10 `auth.login_with_api_key` over verified TLS. Authentication occurs once per persistent session. |
| Authorization | `auth.me` must prove a local account with `READONLY_ADMIN`, `REPLICATION_TASK_READ`, and `CLOUD_BACKUP_READ`, with no full-admin, admin, write, delete, or filesystem-full-control role. |
| Calls | After authentication, only `auth.me`, `disk.query`, `replication.query`, and `cloud_backup.query` are callable. |
| Failure | Authentication, TLS, import, file, API, and role failures produce a sanitized HOLD. Upstream exception text is not chained into the public failure. |
| Authority | `read_only=true`; `control_authority=false`; runtime credential writes are zero. |

API keys are password-equivalent credentials and bypass account 2FA. TrueNAS
also revokes user-linked keys used over insecure HTTP transport. The hard TLS
gate follows the current official [TrueNAS API security guidance](https://www.truenas.com/docs/scale/api/)
and [API-key management guidance](https://www.truenas.com/docs/scale/toptoolbar/managingapikeys/),
inspected 2026-09-02.

## Operator-controlled prerequisites

Before any field observation, the operator must use supported TrueNAS WebUI,
CLI, or API administration—not TruePanel—to:

1. Create a dedicated local service account and a custom privilege containing
   only `READONLY_ADMIN`, `REPLICATION_TASK_READ`, and `CLOUD_BACKUP_READ`.
2. Confirm the account does not inherit `FULL_ADMIN`, `SHARING_ADMIN`,
   `REPLICATION_ADMIN`, `*_WRITE`, `*_DELETE`, or
   `FILESYSTEM_FULL_CONTROL`.
3. Create a user-linked API key with an explicit expiration.
4. Save the key once to an absolute owner-only file and set mode `0600`.
5. Use a hostname covered by the TrueNAS TLS certificate and a certificate
   chain trusted by the Python runtime. Do not use an IP address unless it is
   present in the certificate SAN.
6. Prepare the separately governed restore-receipt directory described in
   `AEGIS_GOVERNED_PASSIVE_RUNTIME.md`.

TruePanel intentionally does not automate these security-sensitive
configuration steps.

## No-deploy observation

After operator review, the installed package can produce one sanitized
stdout-only observation:

```shell
python -m truepanel.aegis.authenticated_observation \
  --incident-id 'recovery:INCIDENT_ID' \
  --receipt-root /absolute/path/to/reviewed/read-only-receipts \
  --api-uri 'wss://truenas.example/api/current' \
  --api-key-file /absolute/private/path/truepanel-readonly.key
```

The key itself is never a command argument. The command does not deploy,
change a service, write a receipt, or mutate TrueNAS. A READY result means only
that the passive runtime's evidence gates passed; it does not authorize repair
or storage writes.

## Deterministic result

HoloDeck proves one positive session and six unsafe branches: rejected
authentication, `FULL_ADMIN`, a directory-backed identity, a secret-bearing
upstream failure, a group-readable key file, and plaintext WebSocket downgrade.

All six unsafe paths produce HOLD. The positive path uses one persistent
connection, one authentication, and three passive calls. Evidence contains
zero credential occurrences, zero mutating calls, and zero runtime credential
writes. Reproduce with:

```shell
pytest -q tests/test_aegis_credential_session.py \
  tests/test_aegis_credential_session_rehearsal.py
python -c "from truepanel.holodeck.aegis_credential_session import run_credential_session_rehearsal as run; print(run()['measurements'])"
```

Preserved evidence:
`docs/evidence/aegis-credential-safe-session-v1.json`.

## Prior art and version boundary

The implementation uses the preinstalled `truenas_api_client` through a
TruePanel-owned factory interface. No client source was copied and no new
dependency was added. The client is LGPLv3; using the system package preserves
its independent replacement boundary.

The stable `TS-25.10.5` client documents `auth.login_with_api_key`. The upstream
development branch now adds SCRAM-SHA-512, channel binding, and key-file-aware
helpers for TrueNAS 26. Those are valuable future improvements, but silently
assuming them on BattleStation's 25.10.5 client would be incorrect. TruePanel
therefore uses the supported 25.10 mechanism only behind verified TLS and does
not auto-downgrade. Revisit the adapter after a TrueNAS 26 upgrade and exact
client-version validation.

## Rejected paths

- `midclt -K RAW_KEY`: key material can appear in process arguments.
- Environment-variable key: secrets can leak through process inspection,
  diagnostics, or inherited environments.
- Local root middleware socket: authentication is credential-free but the
  session is `FULL_ADMIN`, so the role gate correctly holds.
- `--insecure`, plaintext `ws://`, or automatic endpoint downgrade: violates
  TrueNAS API-key transport guidance.
- Automatic service-account, privilege, API-key, or certificate creation:
  changes the host security model and is outside TruePanel's authority.
- Copying the newer TrueNAS 26 SCRAM implementation into TruePanel: version
  mismatch, unnecessary cryptographic maintenance, and LGPL provenance weight.

## Remaining gate

The software boundary is complete, but field validation remains open. The next
step is an operator-reviewed, no-deploy observation on BattleStation using an
expiring least-privilege account and trusted TLS hostname, followed by review of
the sanitized output before any Mission Control runtime wiring.
