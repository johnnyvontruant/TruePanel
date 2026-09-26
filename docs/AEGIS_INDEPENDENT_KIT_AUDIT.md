# AEGIS independent signing-kit audit

## Decision

An export is no longer described as safe to sign after only the audit implemented by
the same TruePanel module that created it. Export now reaches
`READY_FOR_DUAL_AUDIT`. Operator-signature readiness requires matching canonical
witnesses from:

1. `truepanel.aegis.signing_tool`, which reconstructs the packet using the product
   implementation; and
2. `truepanel/holodeck/aegis_independent_kit_auditor.py`, a standalone Python
   standard-library verifier with no TruePanel imports.

The standalone verifier independently defines the schemas, canonical encoding,
derived review card, instructions, exact file set, manifest, authority floor, and
digests. It is run with Python isolated mode (`-I`). Its canonical witness is stored
outside the kit and then compared by the TruePanel dual-audit command. A stale,
extended, noncanonical, missing, or digest-disagreeing witness produces `HOLD`.

This is implementation diversity, not a second human reviewer and not a second
signature. JT remains the sole human approver. Vega's review remains evidence. The
result remains development-only and cannot authorize production, deployment,
hardware, storage writes, networking, or automatic promotion.

## HoloDeck result

The deterministic checkride covers 14 scenarios:

- 1 two-implementation agreement reaches `READY_FOR_OPERATOR_SIGNATURE`;
- 1 disposable external SSHSIG reaches
  `ELIGIBLE_FOR_DEVELOPMENT_CANDIDATE_REVIEW`;
- 12 presentation, transport, session, or witness attacks produce `HOLD`;
- 0 unsafe-ready results, production acceptances, deployments, hardware actions,
  runtime writes, retained fixture keys, TruePanel signer calls, or private-key
  inputs.

The accepted Recovery Coverage Matrix remains 8/8 trusted with zero gaps. The
preserved result is `docs/evidence/aegis-independent-kit-audit-v1.json` (SHA-256
`f609573f555d878484a0143b0f529fe7e6c4ec0eab74874bf013e3ae327a2f45`). The standalone
auditor source is pinned at SHA-256
`53852580f448fcb62db18657d64885df5873ea0a4c1a421e23ec2a61f75273be`.

## Prior-Art Field Report

| Candidate | What was inspected and learned | Fit, maintenance, tests, security | License / provenance | Decision |
|---|---|---|---|---|
| [Diverse Double-Compiling](https://dwheeler.com/trusting-trust/dissertation/wheeler-trusting-trust-ddc.html) | Wheeler's dissertation, formal assumptions, proof, and demonstrations show why agreement from a deliberately diverse implementation can expose a compromised or mistaken primary implementation. | Strongest conceptual match for reducing common implementation failure. It does not make correlated specification errors independent, so the UI says “two implementations,” not “two independent authorities.” | Copyrighted dissertation; ideas only, no text or code copied. | **Adapt the diversity principle.** |
| [Reproducible Builds definition](https://reproducible-builds.org/docs/definition/) | Independent parties should be able to recreate bit-identical artifacts from the same source, environment, and instructions. | Mature cross-distribution practice with extensive tooling and community review. Full build reproducibility is heavier than this four-file packet requires. | Documentation concepts only; no code or schema incorporated. | **Adapt exact-output comparison.** |
| [TUF specification](https://theupdateframework.github.io/specification/) | A trusted root must arrive out of band; hashes shipped beside an artifact do not bootstrap their own trust. | Mature specification and reference implementations. Adding TUF metadata to a local development-only handoff would add unnecessary roles and dependencies. | Community Specification License 1.0 / CC-BY-4.0 text; architectural idea only. | **Adapt out-of-band pinning; do not embed TUF.** |
| [in-toto specification](https://github.com/in-toto/specification/blob/master/in-toto-spec.md) and [reference verifier](https://github.com/in-toto/in-toto) | Strict material/product rules, authorized functionaries, expiry, and threshold checks demonstrate fail-closed chain verification. | Active project with tests and supply-chain focus. Its Python stack and layout model are disproportionate for this narrow, local ceremony. | Apache-2.0 implementation; no code, package, or schema copied. | **Keep as design reference.** |

### Build versus adopt

Build the narrow witness locally. The verifier is 300 lines of standard-library
Python, accepts no credentials, performs no networking, and has a replaceable JSON
witness interface. Adopting a supply-chain framework would save little code while
adding packages, key models, and policy surfaces. The installed OpenSSH SSHSIG
verifier remains the only previously adopted executable behavior and stays behind a
TruePanel-owned interface.

The strongest collaboration opportunity is the Reproducible Builds and TUF
maintainer communities: their experience with independently distributed verifiers
and out-of-band bootstrap material can sharpen how JT obtains and pins the witness
before the first real ceremony.

## Rejected and failed approaches

- Treating the creator's own successful audit as operator-signature readiness.
- Shipping the witness inside the kit it verifies, which would let one compromised
  export replace both artifact and verifier.
- Executing an arbitrary verifier path from TruePanel, which would enlarge the
  command-execution surface.
- Calling the standalone module a second reviewer or signature.
- Assuming implementation diversity prevents a shared specification mistake.
- Adding in-toto, TUF, Sigstore, or a new cryptographic dependency for a four-file
  local packet.

## Remaining boundary

The HoloDeck witness is source-pinned but not yet distributed through an independent
channel. A real ceremony still requires JT's protected development public roster,
an independently pinned copy of the standalone auditor, a clean reviewed candidate
checkout, operator-confirmed UTC, and one offline JT signature. Nothing here
accepts or creates JT's key, installs an envelope, deploys software, or touches
BattleStation.
