# AEGIS Verifier Confirmation Kit

## Outcome

The first JT-owned ceremony step now has a portable, public-only package: one canonical challenge, one human-readable comparison card, and one manifest. The audit reconstructs all three views instead of trusting the manifest as its own root. Only an audited package may create the existing 30-minute development-only operator attestation.

This package does not contain or request a private key, invoke a signer, authenticate JT cryptographically, or prove that its delivery path is independent. It cannot authorize production, deployment, storage, networking, or hardware.

## Architecture

1. TruePanel verifies the already pinned standalone verifier release.
2. Export creates a new `0700` directory with three exclusive `0600` files.
3. The card displays all eight SHA-256 blocks, immutable verifier commit, challenge digest, approved comparison methods, and the authority floor.
4. Audit rejects missing, extra, symlinked, noncanonical, changing, substituted, or mutually rewritten views.
5. Confirmation repeats the audit before comparing the independently observed full digest and creating the expiring receipt from PR #184.

## HoloDeck proof

The deterministic checkride records 14 scenarios:

- 1 exact kit ready for operator comparison
- 1 audited-kit attestation verified
- 10 custody, presentation, display-substitution, or authority attacks held
- 2 unsafe confirmations denied
- 0 private-key inputs, signer calls, cryptographic-independence claims, production acceptances, deployments, hardware actions, or runtime writes

Evidence: `docs/evidence/aegis-verifier-confirmation-kit-v1.json`.

## Prior-art field report

| Candidate | Useful capability | Maturity / maintenance | Fit and dependency weight | License / attribution | Decision |
|---|---|---|---|---|---|
| Signal safety numbers | Complete visual, audible, QR, or separately shared comparison; changed values require fresh approval | Mature production UX with active maintenance | Excellent human-comparison model; application runtime is unrelated | Signal Android is AGPL-3.0-only | Adapt the complete-value and honest identity-limit concepts only; copy no code |
| TUF specification | Initial trusted root delivered out of band; versioned, expiring, threshold-governed metadata | CNCF project and stable specification | Strong trust-bootstrap model but a full TUF client is excessive for this three-file handoff | Community Specification License | Adapt out-of-band bootstrap and reconstruction semantics |
| Sigstore root-signing | Staged signing events, keyholder instructions, preproduction tests, and expiring metadata | Active production trust-root operation | Strong ceremony operations model; multi-keyholder and cloud workflow are heavier than the lone-human development policy | Apache-2.0 | Adapt staged review/test concepts; do not add its runtime |
| OpenSSH fingerprint rendering | Full fingerprints and randomart derived from the actual key | Mature, heavily tested portable implementation | Already installed, but randomart would obscure the exact verifier digest comparison | BSD-style | Keep exact grouped SHA-256 text; no code copied |

### Build versus adopt

Build the small TruePanel-owned kit adapter because the schema and authority boundaries are project-specific. Reuse the installed hashing and JSON primitives; retain OpenSSH only for the later detached-signature boundary. A new TUF, Sigstore, Signal, or QR-code dependency would add substantially more attack surface than verified development time saved here.

### Rejected paths

- A QR code as the only view: difficult to inspect and unnecessary for one operator.
- Randomart as an equality substitute: compact, but less exact than all 64 hexadecimal characters.
- Trusting the manifest after coordinated card-and-manifest edits: the auditor must reconstruct the card independently.
- Exporting into an occupied directory or overwriting a prior kit: stale files could become part of the ceremony.
- Adding a signing convenience command: this step has no need to see private material.
- Claiming the kit proves independent delivery: it is public presentation, not a trust source.

### Collaboration opportunity

The strongest external collaborators are the TUF and Sigstore root-signing maintainers: both communities have direct experience designing operator-facing bootstrap and signing ceremonies that keep presentation, policy, and authority distinct.

## Open risk and next gate

The package is still created from the TruePanel repository channel. JT must obtain the expected SHA-256 independently, audit the exported kit on the comparison device, compare every block, and only then create the short-lived attestation. No real JT evidence was created by this experiment.
