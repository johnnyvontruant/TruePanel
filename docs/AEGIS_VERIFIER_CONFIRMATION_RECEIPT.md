# AEGIS verifier confirmation receipt

## Outcome

The first field-ceremony gate no longer accepts a verifier digest plus a fixed
confirmation string. It now requires a short-lived, content-bound receipt
recording the exact verifier release, full SHA-256, operator-visible comparison
challenge, named out-of-band method, JT's explicit statement, and a 30-minute
validity window.

The receipt is deliberately labeled
`OPERATOR_ATTESTATION_NOT_CRYPTOGRAPHIC_PROOF`. TruePanel can verify its
internal consistency and freshness, but cannot prove that JT actually used an
independent channel or cryptographically authenticate JT before his public key
is provisioned. This limitation stays visible in the schema, result, Mission
Control, and evidence.

## Trust transition

| Input or result | Mechanical guarantee | Explicit limitation |
| --- | --- | --- |
| Content-pinned verifier release | Exact source commit, SHA-256, Git blob, size, and static safety policy | Repository delivery is not independent |
| Comparison challenge | Eight complete digest blocks, approved channel labels, exact operator statement, and authority floor | Displaying a fingerprint does not prove comparison |
| Confirmation receipt | Exact challenge binding, digest match, permitted method, strict shape, and 30-minute freshness | Operator identity and channel are attested, not cryptographically proven |
| Field-ceremony stage | Only a valid receipt advances to public-roster enrollment | No signing, production, deployment, storage, or hardware authority |

The public CLI has separate `challenge`, `confirm`, and `verify` operations. It
accepts no private key, has no signer, follows no symlinks, bounds input size,
detects changing files, and writes no trust state. Receipt output remains
public JSON on stdout so JT controls where it is preserved.

## HoloDeck evidence

Fourteen deterministic scenarios produce one verified operator attestation,
three denied unsafe constructions, and ten holds. Coverage includes wrong
digest, same-repository channel, challenge or receipt extension, challenge and
channel substitution, removed claim, false cryptographic-proof claim,
authority escalation, private-key or signer claims, future timestamps, and
expiry.

There are zero legacy magic-string paths, cryptographic-independence claims,
private-key inputs, signer invocations, production acceptances, deployments,
hardware actions, or runtime writes. The accepted Recovery Coverage Matrix
remains 8/8 trusted with zero gaps.

Preserved evidence:
[`docs/evidence/aegis-verifier-confirmation-receipt-v1.json`](evidence/aegis-verifier-confirmation-receipt-v1.json).
SHA-256: `be5658e859719bb21f01e3e1e79d2b1a5791fca308df94062b3cd5249257d862`.

## Prior-Art Field Report

| Candidate | Actual capability inspected | Maturity / fit / dependency | License / attribution | Recommendation |
| --- | --- | --- | --- | --- |
| [Signal safety numbers](https://support.signal.org/hc/en-us/articles/360007060632-What-is-a-safety-number-and-why-do-I-see-that-it-changed) and [Android comparison code](https://github.com/signalapp/Signal-Android/blob/main/app/src/main/java/org/thoughtcrime/securesms/verify/VerifyDisplayScreenViewModel.kt) | Full numeric comparison or QR scan over another trusted channel; Android code performs exact display-text equality | Mature operator UX and the closest fit for separating display from comparison; importing the GPL application code is unnecessary and incompatible with a tiny MIT interface | Signal-Android is AGPL-3.0; documentation/code cited, nothing copied | Adapt exact-comparison and visible-success/failure semantics only |
| [TUF trusted-root bootstrap](https://github.com/theupdateframework/specification/blob/master/tuf-spec.md#load-trusted-root) | Assumes a trusted root is delivered out of band before in-band updates | Mature security model; directly supports refusing to manufacture initial trust, while a full TUF client is disproportionate here | Specification semantics only; no implementation copied | Adapt the explicit out-of-band trust premise |
| [OpenSSH fingerprint/randomart](https://github.com/openssh/openssh-portable/blob/master/sshkey.c) | Implements multiple public-key fingerprint renderings, including randomart | Mature and dependency-free on TruePanel hosts; randomart improves recognition but may encourage partial visual matching | BSD-style license; no source copied | Keep complete grouped SHA-256 comparison; reject randomart as the authoritative value |
| [Sigstore root-signing](https://github.com/sigstore/root-signing/blob/main/playbooks/tuf-on-ci/SIGNER.md) | Keyholders review an exact signing-event change and contribute signatures separately | Strong operational model, but its multi-keyholder production ceremony exceeds the lone-human development policy | Apache-2.0; no workflow or code copied | Adapt explicit review-event and separately held-key boundaries |

The strongest collaboration opportunity is the Signal safety-number UX and
TUF bootstrap communities: both have deep experience making human comparison
honest without pretending the display channel created trust.

Rejected approaches:

- retaining the fixed magic confirmation string;
- accepting a partial digest, prefix/suffix check, or case-normalized value;
- using randomart, words, or a QR code as the authoritative comparison while
  hiding the complete digest;
- allowing `SAME_REPOSITORY` as an independent method;
- treating the receipt as cryptographic operator authentication;
- accepting an indefinite or future-dated attestation; and
- adding Signal, TUF, Sigstore, or OpenSSH source code or runtime dependencies.

The invalidated assumption was that exact digest equality plus a fixed phrase
was sufficient ceremony evidence. It did not bind the release, method,
operator statement, freshness, or the explicit non-cryptographic evidence
class as one object.

## Safety and next gate

No real confirmation receipt was created. The runtime remains at
`ACTION_REQUIRED_INDEPENDENT_VERIFIER_CONFIRMATION`. JT must obtain the full
verifier SHA-256 through one operator-controlled channel, compare every block,
and create the 30-minute receipt before public-roster enrollment can begin.
