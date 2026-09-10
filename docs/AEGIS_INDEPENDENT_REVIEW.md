# AEGIS independent-review receipts

Project REQUALIFICATION can prove a successor envelope is ready for review, but it must not approve itself. This increment defines an external reviewer receipt whose signatures are checked by an injected verifier.

## Contract

- The signed statement binds the exact candidate, appraisal, predecessor, decision, environment, and validity window.
- Trust policy requires at least two distinct reviewer identities and two valid keys.
- Keys have explicit validity intervals and optional revocation times.
- Expired, revoked, forged, duplicated, incomplete, or digest-mismatched reviews fail closed.
- Success means only `ELIGIBLE_FOR_OPERATOR_PROMOTION`; it does not install an envelope, deploy software, or grant control authority.
- TruePanel contains no production signer or private key. A production verifier must implement the small injected interface.

## HoloDeck pre-upgrade checkride

The deterministic scenario proves the old envelope enters `HOLD` after a simulated TrueNAS 25.10.5 to 25.10.6 transition. Eight receipt paths produce one eligible result and seven holds. One signer, duplicate reviewers, a revoked key, candidate tamper, expiry, a non-ready appraisal, and a forged signature all hold. False eligibility, persisted private keys, installations, automatic acceptances, runtime writes, production mutation, and control authority remain zero.

HMAC exists only inside HoloDeck to exercise protocol semantics. It is not a production recommendation and no lab key is accepted outside that fixture.

## Prior art and build-versus-adopt

- TUF supplies threshold and key-revocation semantics. Adopt the semantics; do not add a complete update framework yet.
- Sigstore supplies identity-bound signatures, short-lived credentials, bundles, and transparency. Preserve the verifier seam for a future Cosign adapter; defer the dependency and hosted trust services until identity and privacy policy are settled.
- SLSA verification summaries reinforce binding the verifier result separately from underlying evidence.
- IETF RATS reinforces separation between evidence, appraisal, and the relying party's final decision.

No external code, schema, binary, dependency, hosted service, credential, or production key was incorporated.

## Rejected paths

- SHA-256 alone as authentication: integrity is not signer identity.
- A single reviewer or duplicate reviewer signatures: insufficient separation of duty.
- Storing private keys in TruePanel: violates the verifier-only boundary.
- Automatic installation after quorum: review evidence is not deployment authority.
- Immediate Sigstore/TUF adoption: valuable future adapters, but premature operational weight for a lab-only contract.

## Reproduction

Run `pytest -q tests/test_aegis_acceptance.py tests/test_aegis_requalification.py`, replay `run_acceptance_checkride()`, validate HANGAR, and run the installed-wheel smoke.

The strongest next step is to choose an operator-owned offline or keyless signing workflow, implement only its public verification adapter, and exercise an isolated staging promotion whose final production action remains manual.
