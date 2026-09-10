# AEGIS Platform Witness

Project PLATFORM WITNESS binds AIRWORTHINESS to one passively observed TrueNAS
release without collecting appliance identity or adding control authority. It
is HANGAR experiment `TP-EXP-0021`.

## Decision boundary

The adapter calls only the documented TrueNAS 25.10.5 `system.version` method.
Its scalar result is normalized to the release component and wrapped with the
cache source, age, observation time, read-only invariants, and a canonical
SHA-256 digest. The output intentionally excludes hostname, serial, hardware,
license, account, network, and credential data.

`system.info` was rejected because its response includes many facts unrelated
to the release decision. Linux kernel and login-banner parsing were rejected
because they are presentation details rather than the supported middleware API.

The witness has three states:

- `VERIFIED`: normalized matching evidence from a live read or fresh cache;
- `REVIEW`: the method is unavailable or only stale display evidence remains;
- `HOLD`: malformed data, an untrusted source, invalid clock, tampering, or a
  known platform mismatch.

AIRWORTHINESS never turns REVIEW into CURRENT, and HOLD never suppresses the
active incident or recovery guidance. The digest detects mutation; it does not
authenticate an issuer or grant authority.

## Deterministic proof

The HoloDeck rehearsal exercises seven paths with one accepted envelope:

| Path | Expected appraisal |
|---|---|
| Matching live release | CURRENT |
| Matching fresh cached release | CURRENT |
| Stale cached release | REVIEW |
| Unavailable release | REVIEW |
| Non-scalar release | HOLD |
| Different normalized release | HOLD |
| Witness with an unapproved field | HOLD |

The first observation performs one `system.version` call. The immediately
cached observation adds zero calls. Measurements are 2 CURRENT, 2 REVIEW,
3 HOLD, zero false-CURRENT paths, zero retained privacy fields, zero runtime
writes, zero production mutations, and zero control authority. Evidence is in
[`evidence/aegis-platform-witness-v1.json`](evidence/aegis-platform-witness-v1.json).

Reproduce with:

```console
pytest -q tests/test_aegis_platform_witness.py tests/test_aegis_assurance.py tests/test_aegis_passive_websocket.py tests/test_aegis.py
python -c "from truepanel.holodeck.aegis_platform_witness import run_platform_witness_rehearsal as run; print(run())"
python -m truepanel.hangar validate --root .
```

## Prior art and provenance

- [TrueNAS `system.version`](https://api.truenas.com/v25.10/api_methods_system.version.html)
  is the supported privacy-minimal release fact.
- [TrueNAS `system.info`](https://api.truenas.com/v25.10/api_methods_system.info.html)
  demonstrates why the broader payload is unnecessary here.
- [IETF RFC 9334](https://www.rfc-editor.org/rfc/rfc9334.html) separates
  evidence collection from appraisal policy.
- [SLSA VSA](https://slsa.dev/spec/v1.0/verification_summary) and
  [in-toto Statement v1](https://in-toto.io/Statement/v1) provide transferable
  subject-and-policy binding semantics.

No external source code, schema, dependency, service, key, or notice-bearing
artifact was incorporated. These sources supplied API facts and architectural
semantics only.

## Limits and strongest follow-up

The deterministic fixture proves contract behavior, not BattleStation API
compatibility. The envelope is integrity-bound but unsigned, and a release
version does not identify hardware or establish remote attestation.

The strongest follow-up is one operator-governed passive observation, then a
rehearsed TrueNAS upgrade. The previous envelope must hold after version drift
until a separately reviewed replacement envelope is issued.
