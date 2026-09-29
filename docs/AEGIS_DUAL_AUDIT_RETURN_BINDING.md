# AEGIS dual-audit return binding

## Outcome

This increment closes a composition gap in the development-only signing ceremony. The exported kit could already be checked by both TruePanel and a standalone standard-library auditor, but the returned-signature verifier did not require that witness. A valid SSHSIG could therefore reach `ELIGIBLE_FOR_DEVELOPMENT_CANDIDATE_REVIEW` without mechanically proving that the exact kit had passed both audits.

The trusted return path now requires the exact kit directory and canonical independent witness. It re-runs the internal audit, compares the three kit digests with the standalone witness, reads the canonical session from that audited kit, verifies the detached signature, reconstructs the source checkout and review materials, and only then returns development-review eligibility.

The signature remains development-only. It grants no production acceptance, deployment, hardware, storage-write, network-change, runtime-write, or automatic-promotion authority.

## Evidence chain

1. Export a public-only kit outside the source checkout.
2. Audit the kit with TruePanel's implementation.
3. Audit the same kit with the independently distributable, standard-library-only verifier.
4. Require digest-identical session, operator card, and manifest results.
5. Sign the canonical session outside TruePanel.
6. On return, repeat steps 2–4 before verifying the signature and reconstructed checkout/materials.

The verifier CLI now derives the session from `--kit` and requires `--independent-witness`. A caller can no longer nominate an unaudited nearby session through `--session`.

## HoloDeck result

The deterministic checkride records eleven scenarios:

- one public kit ready for dual audit;
- one exact kit ready for operator signature;
- one audit-bound returned signature eligible for development candidate review;
- eight fail-closed cases covering a missing witness, stale witness, extended witness, post-audit kit drift, invalid SSHSIG, wrong public roster, materials substitution, and checkout drift;
- zero signature-only eligibility, unsafe-ready results, production acceptances, deployments, hardware actions, or runtime writes.

The accepted Recovery Coverage Matrix remains 8/8 trusted with zero gaps. Preserved evidence is in `docs/evidence/aegis-dual-audit-return-binding-v1.json`.

## Prior-Art Field Report

### Strong candidates inspected

| Candidate | What it supplies | Maturity / testing | Platform and dependency fit | License / attribution | Recommendation and saved work |
| --- | --- | --- | --- | --- | --- |
| [in-toto](https://in-toto.io/) and its [layout/link model](https://in-toto.io/docs/getting-started/) | A supply-chain layout declares ordered steps and authorized functionaries; link metadata makes the chain verifiable rather than trusting isolated attestations. | CNCF project with specifications, reference implementations, and conformance-oriented tooling. | The full framework would add a larger Python dependency and general supply-chain vocabulary than this narrow ceremony needs. Its step-chain semantics map directly. | Apache-2.0. Retain notices if code is incorporated; none was copied here. | **Adapt the idea, do not adopt the runtime yet.** It supplied the key shortcut: verify the complete step chain at the final consumer. Estimated saving: roughly 1–2 design days. |
| [SLSA provenance](https://slsa.dev/spec/v1.2/provenance) and [Verification Summary Attestation](https://slsa.dev/spec/v1.2/verification_summary) | Binds a subject, verification policy, and verifier result while keeping the attestation distinct from the artifact. | Current specification with broad ecosystem adoption and multiple implementations. | Excellent schema inspiration, but adopting a complete attestation stack would be heavy for a local public-only SSHSIG flow. | Specifications are community standards; implementation licenses vary. No SLSA schema or code was copied. | **Adapt subject/policy/result separation.** Keep TruePanel-owned schemas so the mechanism remains replaceable. |
| [The Update Framework specification](https://theupdateframework.github.io/specification/latest/) | Explicit roles, thresholds, freshness, and safe metadata-transition rules. Clients persist trusted state and re-check the chain at consumption time. | Mature security design with multiple production implementations and a published threat model. | Strong conceptual fit for fail-closed trust transitions. A TUF repository is unnecessary for one development operator and would create key/metadata operations outside scope. | TUF specification and reference implementation are Apache-2.0. No code or metadata format was copied. | **Adapt transition discipline; do not deploy TUF here.** The return verifier must not infer trust from an earlier procedural step. |
| [Reproducible Builds: independent verification](https://reproducible-builds.org/docs/independent-verification/) and [role separation](https://reproducible-builds.org/docs/system-images/) | Independent rebuild/check roles make agreement meaningful only when the final comparison is actually consumed. It also emphasizes capturing the environment needed to explain differences. | Long-running cross-project effort with operational experience across distributions. | No runtime dependency. Directly applicable to TruePanel's two audit implementations and the clean-checkout witness. | Documentation is generally CC BY-SA 4.0 unless otherwise noted; this report paraphrases concepts and links the sources. | **Adopt the operational pattern.** Preserve diverse implementations and bind their agreement into the final decision. |
| [OpenSSH SSHSIG protocol](https://github.com/openssh/openssh-portable/blob/master/PROTOCOL.sshsig) | Domain-separated detached signatures and an installed verifier with a negative regression suite. | Mature, actively maintained OpenSSH implementation used by prior AEGIS increments. | Already available on the target development platform, dependency-light, and isolated behind a TruePanel-owned interface. | BSD-style OpenSSH licensing and notices apply to OpenSSH itself; no OpenSSH source was copied. | **Continue adopting the executable protocol adapter.** It avoids adding a signing library while keeping private keys outside TruePanel. |

### Reusable code versus adapted ideas

The only external behavior used is the installed OpenSSH SSHSIG verifier already wrapped by TruePanel. This increment adds no package, service, schema, credential, key, or network dependency. It copies no third-party source.

Adapted architectural ideas are:

- in-toto's continuous, ordered evidence chain;
- SLSA's separation of subject, policy, and verification result;
- TUF's rule that trust transitions are revalidated by the consuming client;
- Reproducible Builds' independent-role comparison;
- OpenSSH's domain-separated detached-signature protocol.

All schemas, orchestration, error states, HoloDeck fixtures, UI language, and tests remain TruePanel-owned and replaceable.

### Rejected approaches

- **Treat the operator signature as implicit proof of the kit audit.** The signature covers session bytes, not the fact that two implementations agreed about the surrounding kit.
- **Trust an earlier `READY_FOR_OPERATOR_SIGNATURE` result.** A procedural checkpoint can become stale or can be skipped unless the final consumer repeats it.
- **Accept an arbitrary `--session` beside an audited kit.** This creates a substitution surface. The trusted verifier now derives the only session path from the exact kit.
- **Embed the signature inside the four-file kit.** That changes the audited object after the witness was produced. The signature remains a separate returned artifact.
- **Adopt a full in-toto, SLSA, TUF, Sigstore, or transparency-log runtime.** These are valuable ecosystems, but the dependency, operations, and trust-root weight exceed this development-only local ceremony.
- **Add a convenience signer.** TruePanel must never accept JT's private key path or invoke a signer.

### Security posture and open risks

The new path fails closed for missing, noncanonical, stale, or mismatched witnesses and for kit, roster, materials, checkout, or signature drift. It does not establish the standalone verifier's independent delivery channel, protect a real JT key, or create a production authorization policy. Those remain explicit gates.

The strongest collaboration opportunity is the in-toto/SLSA maintainer community: TruePanel's narrow step-chain and offline-verification problem is closely aligned with their attestation and functionary models. A future discussion could test whether a small standards-compatible envelope would improve interoperability without importing a heavyweight runtime. No maintainer was contacted.

## Reproduction

```text
pytest -q tests/test_aegis_dual_audit_return.py tests/test_aegis_signing_tool.py tests/test_aegis_independent_kit_audit.py
python -c "from truepanel.holodeck.aegis_dual_audit_return import run_dual_audit_return_checkride as run; print(run()['measurements'])"
python -m truepanel.aegis.signing_tool verify --help
node --check truepanel/web/static/reliability-view.js
python -m truepanel.hangar validate --root .
```

## Strongest next step

JT independently confirms and provisions the protected development public roster, exports one real kit from the pinned candidate checkout, confirms the clock and review card, produces the standalone witness through its independently delivered verifier, signs the canonical session offline, and returns only the detached signature. TruePanel can then run this audit-bound read-only checkride. That result still cannot authorize production, deployment, or hardware action.
