# AEGIS operator-key handoff and prior-art field report

## Result

The single-operator development policy now reaches the real OpenSSH SSHSIG
verification path without putting a private key, signer, production credential,
or deployment authority in TruePanel. A protected public roster must contain
exactly `jt-development-review` and one Ed25519 public key. TruePanel exports a
canonical unsigned statement; JT signs it outside TruePanel; verification can
yield only `ELIGIBLE_FOR_DEVELOPMENT_CANDIDATE_REVIEW`.

Runtime remains `AWAITING_OPERATOR_SIGNATURE` because no JT key or signature was
invented. The HoloDeck checkride creates a disposable fixture key, verifies the
real detached signature, and deletes the complete temporary directory.

## Operator ceremony (not performed)

1. JT creates or selects an operator-owned Ed25519 key outside TruePanel.
2. Only its public key is placed in an owner-controlled, non-symlinked roster:
   `jt-development-review ssh-ed25519 <public-key>`.
3. TruePanel validates the roster and exports the exact canonical statement.
4. JT inspects the packet digest, scope, expiry, and five false authority flags.
5. JT signs offline with `ssh-keygen -Y sign -f <operator-key> -n
   truepanel-aegis-development-review-v1@truepanel <statement.json>`.
6. TruePanel verifies the returned detached signature. It never consumes the
   receipt and cannot use it at a production, deployment, storage, network, or
   hardware boundary.

No production roster location is prescribed by this experiment. Ownership,
backup, revocation, and recovery of JT's real key remain operator decisions.

## Prior-art field report

### OpenSSH SSHSIG — adopt the installed verifier

The [SSHSIG protocol](https://github.com/openssh/openssh-portable/blob/master/PROTOCOL.sshsig)
defines detached armored signatures and a mandatory non-empty namespace to
separate interpretation domains. The current upstream
[regression suite](https://github.com/openssh/openssh-portable/blob/master/regress/sshsig.sh)
tests wrong keys, data, principals, namespaces, validity windows, revocation,
agents, and malformed allowed-signers options. OpenSSH is mature, actively
maintained, already present on the target platform, and BSD-licensed. Adopt its
process boundary; keep TruePanel's strict one-principal/Ed25519 profile and
replaceable adapter. This avoids adding a Python cryptography dependency and
saves an estimated several days of bespoke parsing and verification work.

### TUF — adapt scoped trust, do not adopt the update stack

The [TUF specification](https://theupdateframework.github.io/specification/latest/)
supports explicit roles, per-role key sets and thresholds, offline sensitive
keys, expiry, and key rotation. These are the right semantics for separating a
one-key development role from stronger production roles. A full TUF repository
would add metadata lifecycle and dependency weight that this narrow handoff does
not need. License: CC-BY 4.0 for the specification; python-tuf is Apache-2.0/MIT.
Only the scoped-role and rotation ideas are adapted.

### SLSA VSA and in-toto — adapt subject/policy binding

The [SLSA Verification Summary Attestation](https://github.com/slsa-framework/slsa/blob/main/spec/verification_summary.md)
binds a subject, verifier, policy, input attestations, and result. That model
supports the packet, policy, HoloDeck evidence, and Vega report digests, while
also warning that verifier compromise is outside the attestation's protection.
The specification is Community Specification 1.0; in-toto reference software is
Apache-2.0. Full attestation frameworks are unnecessary for one local handoff,
so only architectural semantics are adapted.

### Sigstore Cosign — defer

[Cosign verification](https://docs.sigstore.dev/cosign/verifying/verify/)
offers keyless identity, transparency-log integration, and hardware-backed key
options. It is mature and Apache-2.0, but adds network/identity/privacy and trust
root decisions that conflict with this offline, single-operator development
ceremony. Reconsider if TruePanel later needs distributed reviewers or public
artifact transparency.

## Rejected paths

- Repository-generated or stored JT private keys: destroys operator ownership.
- Treating Vega evidence as a signature: misrepresents accountability.
- Reusing the production SSHSIG namespace: permits cross-purpose confusion.
- Wildcards, aliases, certificates, roster options, or multiple principals:
  unnecessary ambiguity for one accountable operator.
- Embedding a fixture private key: leaves secret material in history.
- Letting a valid development signature install, deploy, or actuate anything:
  violates the policy and existing safety floor.

The strongest collaboration opportunity is OpenSSH portable: its maintainers
own the protocol and the most complete negative regression corpus. A future JT
conversation should focus on stable programmatic verification interfaces and
hardware-agent behavior, without requesting TruePanel-specific changes yet.

## Evidence and limits

The checkride produced 17 scenarios: one public-roster handoff, one valid
development result, ten fail-closed adversarial cases, and five denied stronger
consumers. Recovery Coverage Matrix remains 8/8 trusted with zero gaps. The
evidence is preserved in `docs/evidence/aegis-operator-key-handoff-v1.json`.

This is HoloDeck evidence, not a field ceremony. No JT public key, JT signature,
production key, service change, runtime write, or live-host observation exists.
