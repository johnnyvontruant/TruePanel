# Project OFFLINE SIGNATURE

Project OFFLINE SIGNATURE replaces HoloDeck's protocol-only HMAC with a
TruePanel-owned adapter for OpenSSH SSHSIG public-key verification. It closes
the authentication seam without placing a production private key or signer in
TruePanel and without granting promotion authority.

## Contract

- The receipt still covers the canonical acceptance statement: exact candidate,
  appraisal, predecessor, promotion request, decision, environment, and time.
- Two distinct reviewer identities and keys remain mandatory.
- The verifier accepts only an absolute operator-owned allowed-signers file
  owned by the current service identity, with no group/world write bit.
- The allowed-signers file and detached signature are size bounded, copied into
  anonymous memory files, and passed to `/usr/bin/ssh-keygen -Y verify` without
  a shell or disk-backed temporary file.
- The namespace is fixed to `truepanel-aegis-review-v1@truepanel`, preventing a
  signature created for another purpose from satisfying AEGIS review.
- Missing OpenSSH support, missing no-follow or anonymous-memory primitives,
  unsafe permissions, malformed signatures, unknown keys, wrong namespaces,
  and verifier timeout all fail closed.
- TruePanel reads public trust material only. Signing remains an external,
  operator-owned action.

OpenSSH public keys may be file-backed, agent-backed, or hardware-backed at the
signer's discretion. That choice is outside TruePanel. A production workflow
must use two separately governed reviewers and must not copy either private key
onto BattleStation.

## No-promotion checkride

HoloDeck creates a disposable validated stage and three disposable Ed25519 key
pairs. It witnesses the actual stage, constructs the exact promotion request,
obtains two simulated external signatures, verifies quorum, and evaluates the
manual gate. The single positive path reaches only
`READY_FOR_MANUAL_PROMOTION`.

Nine negative paths cover one reviewer, malformed signature, untrusted key,
namespace mismatch, unsafe trust-file permissions, missing verifier, request
binding tamper, active incident, and post-review stage tamper. Every path
holds. The checkride never supplies `PROMOTE_TRUEPANEL`, consumes a receipt,
changes a service, or invokes promotion. Its temporary stage and keys are
removed at completion.

Preserved evidence:
[`evidence/aegis-offline-signature-checkride-v1.json`](evidence/aegis-offline-signature-checkride-v1.json).

## Prior art and decision

The OpenBSD [`ssh-keygen(1)`](https://man.openbsd.org/ssh-keygen.1) contract
provides detached signing and verification,
an allowed-signers trust file, signer identity, optional revocation, and a
required application namespace. The OpenSSH
[`PROTOCOL.sshsig`](https://github.com/openssh/openssh-portable/blob/master/PROTOCOL.sshsig)
specification supplies the portable signature envelope. The
[TUF specification](https://theupdateframework.github.io/specification/latest/)
reinforces threshold trust, expiry, and key revocation semantics already
present in AEGIS.

TruePanel adopts OpenSSH as a system verifier behind its existing replaceable
callable interface. It does not copy OpenSSH code, invent cryptography, vendor a
library, add a hosted service, or add a runtime package dependency. Sigstore is
still deferred: its identity and transparency benefits do not yet outweigh its
network, privacy, and trust-root governance decisions for one local NAS.

## Reproduction

```console
pytest -q tests/test_aegis_ssh_verifier.py tests/test_aegis_stage_witness.py tests/test_aegis_promotion_gate.py tests/test_aegis_acceptance.py
python -c "from truepanel.holodeck.aegis_offline_signature import run_offline_signature_checkride as run; print(run())"
python -m truepanel.hangar validate
python development/tools/smoke_installed_wheel.py
```

The strongest next step is to define the operator ceremony and protected
public trust-file installation separately, then perform a read-only preflight
against a real stage. Promotion must remain a separately confirmed manual act.
