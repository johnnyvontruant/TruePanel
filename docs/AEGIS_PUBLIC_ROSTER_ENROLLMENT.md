# AEGIS public-only roster enrollment

Status: development-only experiment. No private key, signature, production
approval, deployment, hardware action, or runtime mutation is created here.

## Result

TruePanel can now convert exactly one operator-confirmed Ed25519 public key into
the narrow `jt-development-review` OpenSSH allowed-signers roster used by the
existing AEGIS handoff. The output is created once, with mode `0600`, outside
the source checkout, then read back and independently parsed before success is
reported. Existing destinations, symbolic links, ambiguous paths, unsafe
permissions, unexpected fingerprints, multiple keys, key options, non-Ed25519
profiles, malformed keys, and private-key files fail closed.

The tool deliberately has no key generator, private-key argument, signer, or
promotion interface. Success means only that public verification material is
ready for the later development-only signing session.

## Prior-art field report

| Candidate | What the code or specification supplies | Maturity and tests | Platform and dependency fit | Security and licensing | Decision |
|---|---|---|---|---|---|
| [OpenSSH SSHSIG and allowed signers](https://github.com/openssh/openssh-portable/blob/master/PROTOCOL.sshsig) | A stable namespace-bound signature format and a roster that maps principals to public keys | Mature, actively maintained, with a dedicated [negative regression script](https://github.com/openssh/openssh-portable/blob/master/regress/sshsig.sh) | Already present on the target platform; no Python package or service | BSD-style OpenSSH license; public-key-only verification avoids secret custody | **Adopt the installed verifier behind TruePanel's interface.** Reuse protocol behavior, not source code. |
| [TUF key and role model](https://theupdateframework.github.io/specification/latest/) | Explicit key IDs, role scope, thresholds, expiry, and out-of-band root bootstrap | Mature specification with broad production use and a security analysis | Semantics transfer well, but a TUF runtime would be excessive for one local development role | Open specification; no copied schema or implementation | **Adapt the least-authority and explicit-role ideas.** Do not add a TUF dependency. |
| [GitHub deploy keys](https://docs.github.com/en/authentication/connecting-to-github-with-ssh/managing-deploy-keys) | A practical example of one public key being deliberately scoped to one resource | Production service with documented read-only defaults and rotation tradeoffs | Familiar operator workflow, but repository access is the wrong authority for AEGIS review | GitHub documentation terms; no code incorporated | **Use only as boundary inspiration.** Never treat a deploy key as review authority. |
| [Sigstore Cosign verification](https://docs.sigstore.dev/cosign/verifying/verify/) | Strong artifact identity and keyless transparency options | Active ecosystem and substantial integration testing | Networked identity and transparency services add weight and availability assumptions to an offline NAS ceremony | Apache-2.0 implementations; service and identity-policy obligations | **Defer.** Reconsider if TruePanel later needs multi-host public release attestations. |
| Minisign | Small public-key signature workflow | Mature and intentionally simple | Would add a second signature stack beside the OpenSSH dependency already required | ISC license; compatible, but redundant | **Reject for this increment.** It saves no verified development time after SSHSIG adoption. |

Capability, maintenance, test quality, dependency weight, platform fit,
security posture, and license compatibility all favor the installed OpenSSH
verifier. The estimated shortcut is avoiding a new cryptographic parser,
signature dependency, key format, and associated negative-test surface. The
TruePanel-owned enrollment interface remains replaceable and constrains the
upstream behavior to one principal, one Ed25519 public key, and one development
namespace.

No third-party code, schema, package, service, credential, key, or dataset was
copied. The implementation calls the installed OpenSSH verifier only through
the existing TruePanel adapter. Attribution is preserved here and in the
predecessor signing reports.

## Rejected and failed paths

- Accepting a private key and calling `ssh-keygen -y` was rejected. Even if the
  output is public, it would make TruePanel a secret-handling component.
- Generating JT's key in the repository or HoloDeck was rejected. Fixture keys
  remain disposable simulation material and are destroyed with the checkride.
- Wildcard principals, multiple identities, key options, certificates, RSA,
  and shared production namespaces were rejected as wider than the approved
  lone-human development policy.
- Replacing an existing roster was rejected. Rotation must be a separate,
  content-bound ceremony rather than an enrollment side effect.
- Writing the roster inside the checkout was rejected because a public key is
  still trust configuration and must not silently travel with source changes.
- The first parser incorrectly limited an OpenSSH public-key comment to one
  word. The corrected parser treats all trailing comment text as non-identity
  metadata and constructs the roster only from key type and key blob.
- GitHub deploy-key reuse was rejected because repository access and AEGIS
  review are distinct authorities.

## Verification and evidence

The deterministic HoloDeck checkride records 16 scenarios: one roster
provisioned, one existing handoff ready for an offline signature, and 14
adversarial holds. It records zero unsafe-ready outcomes, private keys accepted,
keys generated by TruePanel, signer invocations, production acceptances,
deployments, hardware actions, or runtime writes. The accepted Recovery
Coverage Matrix remains 8/8 trusted with zero gaps.

Preserved evidence:
[`docs/evidence/aegis-public-roster-enrollment-v1.json`](evidence/aegis-public-roster-enrollment-v1.json).

## Collaboration opportunity

OpenSSH portable maintainers are the strongest technical collaboration target
for long-term SSHSIG and allowed-signers compatibility guidance. TUF
maintainers are the strongest policy-design target if TruePanel later needs
safe operator-key rotation or multiple scoped roles. No external contact was
made.

## Next gate

JT independently confirms the public-key fingerprint through a trusted view,
provisions the development-only roster, dual-audits one real public signing
kit, signs the canonical session outside TruePanel, and returns only the
detached signature. That checkride remains read-only and cannot authorize
production, deployment, storage, network, or hardware control.
