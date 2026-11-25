# AEGIS compromise-time signature validity

## Decision

AEGIS now separates a reviewer's mathematically valid SSH signature from its
eligibility to count toward historical review quorum. The signature is eligible only
when its exact payload authenticates, its reviewer fingerprint matches, the governing
root transition is dual-signed, and its signed time is strictly before any recorded
compromise time for that fingerprint. A signature at the compromise instant or later
remains `HOLD`.

This is a deterministic simulation contract. It grants no field-validation,
installation, deployment, runtime-write, network, storage, or hardware authority.

## Verification path

1. Verify the canonical root-rotation statement with both predecessor and successor
   root keys.
2. Verify the exact review statement and SSHSIG in the existing review namespace.
3. Bind the statement's reviewer fingerprint to the protected allowed-signers roster.
4. Select at most one matching compromise event from the trusted rotation.
5. Compare the statement's signed time with the compromise time using a strict
   pre-compromise boundary.
6. Preserve the result and every failure as HoloDeck evidence; only accepted results
   are eligible for reviewer quorum.

## HoloDeck evidence

The six-scenario checkride accepts one pre-compromise signature and one unaffected
reviewer, holds signatures exactly at and after compromise, and rejects an untrusted
root transition and an authority-escalated review. All eight Recovery Coverage Matrix
entries remain trusted. The fan-degradation fixture still correlates shared cooling at
sample 19 versus isolated thresholds at sample 46, a 27-sample lead. No fixture key is
retained and every operational action counter is zero.

Evidence: `docs/evidence/aegis-temperature-reviewer-signature-validity-v1.json`

## Prior-Art Field Report

| Candidate | What the actual specification or code supplies | Fit and maturity | License / attribution | Recommendation |
| --- | --- | --- | --- | --- |
| Sigstore threat model and trust root | Directly specifies compromise timestamps so legitimate pre-compromise signatures remain verifiable; its trust-root protobuf retains historical authorities and explicit validity ranges | Mature production architecture and the closest semantic match; adopting Sigstore services would add network and trust dependencies | Documentation and protobuf specifications are Apache-2.0; concept only, no code copied | **Adapt the semantics now.** Keep the TruePanel-owned interface and evaluate a timestamp witness later. |
| Sigstore timestamps / Rekor | Countersigned RFC 3161 timestamps bind immutable time to the signature; Rekor inclusion provides a transparency witness, with documented clock limitations in v1 | Strong next step for independently witnessed time; disproportionate for an offline deterministic fixture today | Apache-2.0 ecosystem; no runtime or source incorporated | **Prototype later** behind a replaceable timestamp-evidence interface. |
| RFC 3161 | Standard protocol for proving that a datum existed before a time, including the historical-signature check that revocation occurs after the trusted timestamp | Stable standard and vendor-neutral, but requires a TSA and certificate/revocation policy | IETF standard; attribution link retained, no implementation copied | **Adopt as the future external-time profile**, not as a current dependency. |
| TUF compromise resilience | Fast key replacement, offline roots, distinct roles, and threshold signatures; current root metadata replaces compromised keys | Excellent root-rotation architecture, but it does not make a signer-asserted payload time independently trustworthy | Specification/reference implementations have permissive licenses; ideas only | **Retain the already-adapted dual-root design.** Do not treat rotation alone as proof of signing time. |
| OpenSSH SSHSIG | Existing dependency-light signature authentication and namespace separation | Excellent local cryptographic primitive, but SSHSIG itself does not supply trusted signing time | OpenSSH portable license already honored by the project; existing executable only | **Keep**, wrapped by TruePanel policy and explicit time evidence. |

### Incorporated shortcut and provenance

No third-party code or dependency was incorporated. The implementation adapts
Sigstore's documented compromise-time rule and RFC 3161's separation between signature
validity and trusted time, while reusing TruePanel's existing OpenSSH verifier and
dual-root contract. All behavior is behind
`evaluate_temperature_reviewer_signature_validity`, so an RFC 3161 or transparency-log
witness can replace the current time assertion without changing callers.

### Rejected paths

- Accepting every cryptographically valid historical signature: a stolen key could
  backdate a payload and still verify.
- Treating `prepared_at_utc` as independently trusted: it is inside signer-controlled
  content and has no external clock witness.
- Adding a remote TSA or transparency service now: it would introduce network,
  availability, privacy, credential, and operational dependencies before a provider
  policy exists.
- Copying a full Sigstore/TUF client: dependency weight and unrelated distribution
  machinery exceed this narrowly scoped verification contract.

## Known limitation and next step

The current `prepared_at_utc` value is authenticated but signer-asserted. This closes
the policy gap and fails closed on known compromise chronology; it does **not** prove
when the signature was actually created. The strongest next increment is a
TruePanel-owned timestamp-evidence interface with a deterministic RFC 3161 fixture,
then an optional monitored transparency or TSA adapter. Sigstore trust-root and
verification maintainers are the strongest collaboration candidates because their
public model already combines compromise time, historical verification, timestamp
authorities, and transparency evidence.
