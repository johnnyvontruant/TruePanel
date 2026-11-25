# AEGIS authenticated temperature development acceptance

## Decision

The temperature-telemetry coverage candidate may reach development review only
when JT's exact, short-lived acknowledgement is verified as an OpenSSH SSHSIG
signature from the protected `jt-development-review` public-key roster. This
does not accept or install the candidate and grants no production, deployment,
storage, network, or hardware authority.

The live Mission Control state contains neither JT's acknowledgement nor a
signature, so it remains `ACTION_REQUIRED_OPERATOR_CONFIRMATION`. HoloDeck uses
disposable fixture keys only; it removes them before returning evidence.

## Architecture and trust boundary

The signed canonical statement binds the complete development acceptance
record, its exact candidate and appraisal subjects, its expiration, the fixed
development-only scope, and every negative authority flag. Verification uses
the existing `OpenSshSignatureVerifier` behind a TruePanel-owned callable
interface. The adapter snapshots an absolute, owner-controlled, non-symlink
allowed-signers file; permits exactly one Ed25519 identity; invokes the
installed `/usr/bin/ssh-keygen -Y verify`; and treats every error as rejection.
TruePanel never accepts a private-key path and contains no signing operation.

The dedicated namespace
`truepanel-aegis-temperature-development-v1@truepanel` prevents a signature
from an older AEGIS ceremony or another protocol from being reused here.

## HoloDeck proof

`run_temperature_authenticated_acceptance_checkride()` executes the real
OpenSSH signing and verification protocol with two temporary fixture keys.
Eleven cases produce one confirmation-required result, one signature-required
result, one authenticated development-review result, and eight HOLD results.
Negative cases cover signature corruption, wrong namespace, a foreign key
under the same principal, confirmation replay, expiry, unsafe roster mode,
symlinked roster, and verifier namespace substitution.

There are zero production keys, retained fixture keys, runtime acceptances,
candidate installations, deployments, writes, or hardware actions. Preserved
evidence is in
[`docs/evidence/aegis-temperature-authenticated-acceptance-v1.json`](evidence/aegis-temperature-authenticated-acceptance-v1.json)
with self-digest
`fbc38c2dcee69042f75d6bd1c3297848510198ebadfb2dde65e4f19e5bd8c66a`,
independently replayed by the test suite.

## Prior-art field report

| Candidate | What the implementation or specification supplies | Maturity / tests / maintenance | Platform, dependency, security, and license fit | Recommendation |
| --- | --- | --- | --- | --- |
| [OpenSSH SSHSIG protocol](https://github.com/openssh/openssh-portable/blob/master/PROTOCOL.sshsig), [`sshsig.c`](https://github.com/openssh/openssh-portable/blob/master/sshsig.c), and [negative regression suite](https://github.com/openssh/openssh-portable/blob/master/regress/sshsig.sh) | Detached signatures, an explicit interpretation namespace, message hashing, principal-to-public-key authorization, and fail-closed wrong-key/data/namespace cases | Mature OpenSSH code; actively maintained as of 2026-10-10; extensive upstream positive and negative regressions | Already installed on the target Linux family; no Python crypto dependency or service; ISC-style permission terms in `sshsig.c`, regression file public domain; executable use adds no copied code or notice obligation | **Adopt** the installed verifier behind TruePanel's narrow adapter. This is the strongest shortcut and collaboration opportunity; OpenSSH maintainers are the people to approach about edge-case compatibility. |
| [in-toto Statement v1](https://github.com/in-toto/attestation/blob/main/spec/v1/statement.md) | Digest-bound immutable subjects and an explicit predicate type | CNCF project with a stable v1 specification and cross-ecosystem use | Useful data-model semantics, but adding its libraries would add weight without replacing operator key verification; Apache-2.0 for repository code | **Adapt the idea**, not code or schema: bind exact subject digests in TruePanel's deliberately narrower statement. |
| [The Update Framework specification](https://github.com/theupdateframework/specification/blob/master/tuf-spec.md) | Scoped roles, offline trust, expiration, thresholds, rollback/freeze defenses, and separation between verified metadata and installation | Mature CNCF specification, current version 1.0.37 dated 2026-10-08 | Strong architectural guidance, but a full update framework is excessive for one development-review receipt; specification content is CC-BY 4.0 | **Adapt role and authority separation**. Do not imply that authenticated metadata grants installation authority. |
| Sigstore Cosign | Keyless and key-based artifact verification, transparency-log integration, policy-oriented CI workflows | Active, well tested, broad ecosystem adoption | Valuable for public release provenance, but adds binaries/services, online identity and transparency dependencies, and a larger operational surface than this offline single-operator ceremony; Apache-2.0 | **Defer** until TruePanel publishes broadly distributed release artifacts. |

No third-party code, schema, package, service, credential, public key, or dataset
was copied or added. The only adopted component is the already-installed
OpenSSH verifier, isolated behind TruePanel's interface. The retained source
links provide provenance; no additional attribution file is required for
process invocation.

## Rejected and failed paths

- Treating the unauthenticated acknowledgement from TP-EXP-0024 as sufficient
  would preserve ambiguity about who approved it.
- Appending a character to an armored signature did not reliably corrupt it:
  OpenSSH ignores bytes outside the armor boundary. The rehearsal now mutates
  the base64 payload itself.
- Deferring unsafe-roster verification until after permissions were restored
  accidentally tested the safe state. The checkride now evaluates while the
  file is actually group/world-writable.
- A repository-generated or repository-retained JT private key would collapse
  the trust boundary and is prohibited.
- Cosign, in-toto libraries, and a full TUF client are disproportionate here;
  their architectural ideas are useful but their extra dependencies do not
  improve this exact offline verifier.

## Open risks and next step

The success path is laboratory proof with disposable keys, not a real JT
authorization. The candidate remains 9/9 but unaccepted and uninstalled; the
accepted Recovery Coverage Matrix remains 8/8. The next step is for JT to
provision only the protected development public roster and sign the exact
exported statement offline, followed by a read-only verification checkride.
Any installation proposal must remain a separate, explicitly reviewed step.
