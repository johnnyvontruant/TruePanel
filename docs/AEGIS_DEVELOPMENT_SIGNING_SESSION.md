# AEGIS development signing session and prior-art field report

## Result

The development receipt, clean Git commit and tree, preflight handoff, public-key
fingerprint, and JT-confirmed UTC observation now form one canonical SSHSIG
statement under a new development-only namespace. Verification reconstructs the
session from the checkout and current evidence before it can return
`ELIGIBLE_FOR_DEVELOPMENT_CANDIDATE_REVIEW`.

This closes a gap in the earlier handoff: JT could sign the receipt while the
checkout and clock witnesses remained unsigned presentation data. A signature
over the new session cannot be replayed as an old receipt signature, used in the
production namespace, or detached from its commit tree. The Git inspection is
read-only, uses fixed argument vectors without a shell, disables replacement
objects, requires an absolute non-symlinked repository root, and rejects tracked
changes, untracked files, wrong commits, and dirty submodules.

The clock witness is deliberately called **operator-confirmed UTC**. TruePanel
does not claim that a local clock is an external timestamp authority. JT must
compare the displayed UTC value before signing; the signature then makes that
observation accountable and immutable. A future RFC 3161 or Roughtime adapter
could strengthen provenance without changing the session's TruePanel-owned
interface.

Mission Control keeps its mobile development-only panel and now names the three
signing-session prerequisites: clean pinned checkout, commit tree, and
operator-confirmed UTC. It still shows no production, deployment, hardware, or
storage-write authority.

## Prior-art field report

| Candidate | Actual contract inspected | Capability / maturity / fit | Decision and licensing |
| --- | --- | --- | --- |
| [OpenSSH SSHSIG](https://github.com/openssh/openssh-portable/blob/master/PROTOCOL.sshsig) and [negative tests](https://github.com/openssh/openssh-portable/blob/master/regress/sshsig.sh) | Application namespaces and signed message hashing; wrong namespace, identity, key, and content fail verification. | Mature and already installed; avoids introducing a cryptographic parser or private-key API. | Adopt the executable behind TruePanel's replaceable adapter under its BSD-style licensing. No code copied. |
| [in-toto Statement v1](https://github.com/in-toto/attestation/blob/main/spec/v1/statement.md) and [attestation-verifier prototype](https://github.com/in-toto/attestation-verifier) | Subjects carry digests, while the example verifier links clone materials to later test/build products. Current attestation releases explicitly recognize `gitCommit` and `gitTree` digest algorithms. | Strong conceptual match, but the verifier README explicitly says it is a prototype and must not be used in production; it would also add a second runtime and schema. | Adapt subject-digest and linked-evidence semantics. Apache-2.0 ecosystem; reject the prototype as a dependency and copy no code or schema. |
| [SLSA provenance v1.2](https://slsa.dev/spec/v1.2/provenance) | Provenance binds subjects, external parameters, resolved dependencies, and build timing in one authenticated claim. | Excellent model for keeping source identity and verification inputs inside the signed object; full build provenance is broader than this operator ceremony. | Adapt the single authenticated-claim principle, not its wire format. Specification/educational use only. |
| [Git porcelain status](https://git-scm.com/docs/git-status#_porcelain_format_version_1) and [rev-parse](https://git-scm.com/docs/git-rev-parse) | Stable machine-readable cleanliness status plus explicit commit/tree object resolution. | Native, mature, zero added package; platform fit is exact. It cannot prove remote availability or trusted wall time. | Adopt through fixed read-only subprocess calls. Git is GPL-2.0; TruePanel invokes the installed executable and copies no code. |
| [RFC 3161 timestamp protocol](https://www.rfc-editor.org/rfc/rfc3161) | A timestamp authority signs a hash and trustworthy time value. | Stronger time provenance, but requires an external authority, trust roots, privacy review, and online availability. | Defer behind a future clock-witness adapter; do not add a hosted dependency to the offline development gate. |

The strongest collaboration opportunity is the in-toto Attestation Framework
community because its newly explicit Git commit/tree digest vocabulary maps
directly to this session subject. OpenSSH remains the best implementation
shortcut. No maintainer was contacted.

## HoloDeck proof and limits

The preserved checkride has 11 scenarios: one signing-ready session, one exact
fixture signature eligible for development review, and nine HOLD results. HOLD
coverage includes missing or wrong signatures, clock and checkout substitution,
tree tampering, authority escalation, dirty checkout before and after signing,
and receipt replay. False-ready outcomes, production acceptances, deployments,
hardware actions, and runtime writes are zero. Recovery Coverage Matrix remains
8/8 trusted with zero gaps.

The checkride uses a disposable Ed25519 key and temporary Git repository. It is
not JT's signature, a timestamp-authority proof, acceptance of the v2 Recovery
Coverage Matrix, or permission to merge, install, deploy, or actuate hardware.
The next real gate remains operator-owned provisioning and a separate manual
offline signature over a freshly reconstructed session.
