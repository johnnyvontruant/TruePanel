# AEGIS roster-enrollment binding

## Outcome

The field-ceremony consumer no longer advances on an arbitrary syntactically
valid `jt-development-review` allowed-signers entry. It requires the exact
public roster, a canonical enrollment receipt, and the fingerprint JT compared
outside TruePanel. It reconstructs all three before naming signing-kit export
as the next action. Missing, substituted, writable, symlinked, or
authority-expanded evidence produces `HOLD`.

The receipt is deliberately unsigned public evidence. It records and binds the
enrollment ceremony but does not authenticate JT, prove how the fingerprint
was obtained, or grant production, deployment, hardware, storage, network, or
automatic-promotion authority.

## Architecture and failed path

The earlier final consumer called OpenSSH roster inspection directly. OpenSSH
correctly checked the principal and key, but the consumer had no independent
expected fingerprint and no record binding the roster to TruePanel's exclusive
enrollment path. A different Ed25519 key under the same principal therefore
passed that stage. The new audit compares the protected roster bytes, their
SHA-256, the exact key fingerprint, the canonical receipt, and the fixed
development-only authority map. A raw roster is now incomplete context.

HoloDeck records eight scenarios: one exact enrollment-bound path advances only
to `ACTION_REQUIRED_SIGNING_KIT_EXPORT`; seven adversarial paths hold. These
include raw-roster-only input, same-principal key substitution, fingerprint
substitution, receipt mutation, authority extension, symlinked evidence, and a
writable receipt.

## Prior-Art Field Report

Research was refreshed on 2026-10-06 by inspecting the actual specifications,
implementation, tests or operating documentation rather than project blurbs.

| Candidate | What the inspected work supplies | Maturity / fit / dependency | License and recommendation |
| --- | --- | --- | --- |
| [OpenSSH SSHSIG protocol](https://github.com/openssh/openssh-portable/blob/master/PROTOCOL.sshsig) and [`sshsig.c`](https://github.com/openssh/openssh-portable/blob/master/sshsig.c) | Detached signatures, namespace separation, and exact allowed-signers key/principal matching. The C verifier checks the presented key against each allowed-signers line and enforces namespace and validity options. | Mature, widely deployed, existing system executable; excellent platform fit and no new package. It verifies the supplied roster but does not establish how that roster was enrolled. | BSD-family collection. **Adopt installed verifier behind TruePanel's interface; add TruePanel-owned enrollment provenance checks.** |
| [TUF specification](https://github.com/theupdateframework/specification/blob/master/tuf-spec.md) | Client-side trust reconstruction, explicit roles and keys, threshold policy, expiry, and resistance to mix-and-match state. Its goals distinguish key identity from untrusted transport. | Mature standard with multiple implementations, but a full TUF repository would be disproportionate for one development-only roster. | Community Specification License 1.0; implementation is permitted, while derivative specification text requires attribution. **Adapt the idea that the final consumer reconstructs trusted-key state; do not import the framework here.** |
| [Sigstore root-signing](https://github.com/sigstore/root-signing) | Real operational model: named keyholders inspect proposed trusted-root changes, sign with personal hardware keys, stage non-trivial changes, run generic and client-specific tests, then publish. | Active production trust-root operation with strong tests; its multi-key ceremony is intentionally stronger and heavier than TruePanel's lone-human development policy. | Apache-2.0. **Use as operating-model inspiration, not code.** Its maintainers are the strongest collaboration opportunity for reviewing the boundary between public ceremony evidence and authenticated trust-root changes. |
| [in-toto Statement v1](https://github.com/in-toto/attestation/blob/main/spec/v1/statement.md) | A typed statement binds an assertion to immutable subjects by digest; consumers may apply policy to names and digests. | Mature attestation vocabulary and clean conceptual fit. Adding its libraries or envelope format would add weight without authenticating this unsigned receipt. | Apache-2.0. **Adapt subject/digest binding semantics only.** |

No third-party code, schema, package, service, credential, key, or dataset was
copied. OpenSSH and Git remain external executables behind TruePanel-owned
interfaces. The new JSON is a TruePanel schema and all behavior is covered by
replaceable local tests.

### Rejected shortcuts

- Treating the allowed-signers principal as key provenance: a principal is a
  policy label, not proof that JT compared that key's fingerprint.
- Trusting the receipt alone: it is unsigned and cannot authenticate its own
  producer.
- Embedding or generating JT's private key: unnecessary and contrary to the
  single-operator boundary.
- Adding TUF, Sigstore, or in-toto runtimes: dependency weight and ceremony
  semantics exceed this development-only need and still would require an
  external operator trust bootstrap.
- Claiming the operator-confirmed fingerprint is cryptographic identity: it is
  explicit public input whose real-world comparison remains JT's action.

## Safety and next gate

All proof uses disposable HoloDeck keys and public artifacts. The exact path
stops before signing-kit export and cannot sign, accept a development
candidate, install, deploy, or actuate anything. The strongest next step is for
JT to compare the real public-key fingerprint through a protected channel,
provision the public roster and canonical receipt, and let this consumer
re-audit both before exporting one public signing kit.
