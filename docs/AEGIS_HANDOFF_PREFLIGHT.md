# AEGIS pre-signing checkride and prior-art field report

## Finding and correction

The PR #164 handoff constructor checked its public key, packet digest and
namespace, but could still emit an apparently signing-ready bundle for an
expired receipt, an unreviewed candidate, missing HoloDeck proof, a coverage
gap, or a widened authority field. Its subsequent verifier held these cases;
the misleading *request to sign* was the failed path. This follow-up rejects
them before JT is asked to sign. Its signature verification still rechecks all
conditions, so preflight does not confer approval.

The caller supplies a separately established, 40-character lowercase source
commit and current time. The constructor requires the packet and candidate to
match that commit, checks the exact policy and packet fields, all evidence
digests, rehearsal, coverage, Vega report, operator identity, scope, freshness,
and maximum age; only the as-yet-unavailable signature may fail. Invalid
inputs raise a bounded error instead of exporting a bundle.

The public-key fingerprint printed in the handoff is now checked again on the
protected roster snapshot used by OpenSSH verification. This closes a roster
rotation/substitution interval between inspecting the handoff and using it.
The old 17-scenario evidence remains preserved; its expired-case reason is now
an earlier HOLD, so exact v1 reason-string replay is superseded by the new
26-scenario checkride.

## Prior-art field report

| Candidate | Code or contract inspected | Fit / maturity / license | Decision |
| --- | --- | --- | --- |
| [OpenSSH SSHSIG](https://github.com/openssh/openssh-portable/blob/master/PROTOCOL.sshsig) and [regression corpus](https://github.com/openssh/openssh-portable/blob/master/regress/sshsig.sh) | Namespace prevents cross-purpose use; wrong-key, wrong-data and wrong-namespace negative cases use real signing and verification. | Mature, maintained, installed on the target platform; portable OpenSSH has BSD-style licensing; no additional Python dependency. | Adopt the existing executable through TruePanel's adapter and pin the fingerprint on the verification snapshot. No code copied. Saves days of cryptographic/parser work. |
| [TUF specification](https://theupdateframework.github.io/specification/latest/) | Roles and keys, threshold trust, offline sensitive keys, expiry and migration. | Mature architecture; specification CC BY 4.0; full updater metadata and client are excessive for a local development approval. | Adapt scope/expiry semantics, not its metadata code. |
| [in-toto verifier](https://github.com/in-toto/in-toto/blob/develop/in_toto/verifylib.py) | Layout/link verification distinguishes supplied evidence from validated steps and fails on missing threshold links. | Actively used, Apache-2.0; full supply-chain layout engine adds a separate runtime and schema. | Adapt the principle that all required evidence must be evaluated before a result can be claimed. No code copied. |
| [SLSA VSA](https://github.com/slsa-framework/slsa/blob/main/spec/verification_summary.md) | Subject digest, policy, input attestations and result are distinct fields; consumers verify each. | Mature specification ecosystem; specification provenance/attribution governed by SLSA and OpenSSF documentation licenses. | Adapt subject/policy/result separation, not the wire format or a hosted verifier. |

The best collaboration opportunity remains OpenSSH portable maintainers: their
negative SSHSIG corpus and verification contracts are the strongest upstream
shortcut. No maintainer was contacted, and no new external code, package,
schema, service or credential was introduced.

## Checkride and limits

The new [evidence](evidence/aegis-operator-key-preflight-v1.json) has 26
deterministic scenarios: one signing-ready, one valid *fixture* development
receipt, 19 HOLD and five stronger-consumer DENIED. Nine of the HOLD scenarios
now occur before signing (expiry, source drift, unknown field, authority
escalation, policy age, candidate change, failed rehearsal, coverage gap and
review blocker). A disposable lab key is removed after rehearsal. Recovery
Coverage Matrix remains 8/8 trusted, zero gaps.

The externally supplied source commit and time still need independent
establishment from a validated, pinned checkout and trusted clock. The existing
fixture's placeholder commit and simulated key do not prove JT's real packet.
No JT public roster or signature has been provisioned. This change cannot
accept a coverage candidate, install an envelope, deploy, or actuate anything.
Mission Control remains in `AWAITING_OPERATOR_SIGNATURE`; no UI status is
invented. A future development-candidate consumer must independently verify
the receipt instead of trusting its result label alone.
