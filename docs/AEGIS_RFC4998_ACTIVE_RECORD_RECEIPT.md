# AEGIS RFC 4998 active-record receipt

## Outcome

AEGIS now has a fail-closed, per-record receipt join for the existing Bouncy
Castle 1.86 and European Commission ETSI DSS 6.5.1 validators. The join names
one immutable EvidenceRecord and one detached object by digest, requires the
two exact validator products and versions, checks every security verdict, and
preserves each canonical input-receipt digest. Each upstream job separately
byte-compares its receipt before upload. A same-run CI job downloads the two
validator artifacts, joins them, byte-compares the result with the reviewed
receipt, and uploads the aggregate receipt.

This is a deterministic HoloDeck rehearsal. It proves the verification path,
not a production record. Mission Control therefore shows the per-record
contract as rehearsed while the active runtime record remains `PENDING`.

## Architecture

| Component | Responsibility |
| --- | --- |
| Active-record manifest | Names the record, profile, exact record SHA-256, detached-data SHA-512, and required oracle versions. |
| Oracle adapters | Validate the exact bytes through pinned public Bouncy Castle and DSS APIs and emit narrow receipts. |
| `rfc4998_active_receipt` | Rejects missing, duplicate, unexpected, stale-version, mismatched-subject, incomplete-verdict, and authority-escalating receipts. |
| HoloDeck | Rehearses one accepted pair and seven adversarial holds without network, storage, runtime, or hardware authority. |
| Mission Control | Shows the rehearsed contract, required validators, and still-pending active record on the mobile reliability panel. |
| CI | Joins artifacts produced by the same workflow run, diffs the deterministic receipt, and preserves it as a separate artifact. |

## Prior-art field report delta

| Candidate | Actual material inspected | Capability, maturity, and fit | License / security / weight | Decision |
| --- | --- | --- | --- | --- |
| [in-toto Attestation Framework v1](https://github.com/in-toto/attestation/blob/main/spec/v1/statement.md) | Statement subject/digest binding, predicate separation, and validation model | The strongest small abstraction for binding claims to immutable subjects. Full DSSE signing is premature because these receipts are same-run CI evidence, not authenticated production attestations. | Apache-2.0 project; no library, schema, or source copied. Original TruePanel JSON uses only the subject-digest architectural idea. | **Adapt now:** named digest subjects and explicit predicate-like verdicts behind a TruePanel-owned join. **Defer DSSE** until a production attester identity exists. |
| [SLSA Provenance v1](https://slsa.dev/provenance/v1) | Subject and resolved-dependency provenance model, downstream verification rules | Excellent for describing how build outputs were produced, but AEGIS validates preservation evidence rather than a software build. | Community Specification License 1.0 / mixed legacy Apache-2.0; no specification text or code copied. | **Architectural reference only:** preserve validator versions and receipt digests, without claiming SLSA provenance. |
| [Sigstore bundle](https://docs.sigstore.dev/about/bundle/) | Offline verification material, RFC 3161 timestamps, DSSE/in-toto payloads, transparency-log evidence | Strong future envelope once receipts have an authenticated issuer and public-verifiability requirement. Public infrastructure and identity/network surfaces would widen the current trust boundary. | Apache-2.0 ecosystem; no dependency or network integration added. | **Defer:** do not introduce Fulcio, Rekor, Cosign, credentials, or public logging for a local simulation receipt. |
| [ETSI DSS evidence-record validation](https://ec.europa.eu/digital-building-blocks/DSS/webapp-demo/doc/dss-documentation.html#evidence-records) | RFC 4998 validation, detached contents, archival validation, diagnostic reports | Already supplies the second policy-rich validator. Its broader report is useful but less stable than the narrow join contract. | LGPL-2.1-or-later, development/CI only; explicit trust root and no network validation sources. | **Reuse existing adapter:** preserve the narrow receipt; do not expose DSS report internals as AEGIS policy. |

### Rejected paths

- Treating two receipts as sufficient without checking their record and
  detached-data digests was rejected; it permits a split-subject false pass.
- Accepting any two validator names or versions was rejected; the manifest is
  the reviewed oracle policy.
- Signing the aggregate with a new CI-generated key was rejected because an
  ephemeral key adds ceremony without an independently trusted identity.
- Adding Sigstore public services was rejected for this phase because it adds
  network, identity, credential, and transparency-log authority unrelated to
  deterministic HoloDeck verification.
- Promoting `DUAL_ORACLE_REHEARSED` to production trust was rejected. A real
  active record still needs fresh matching receipts, authenticated custody,
  clock/revocation review, and an approved trust policy.

## Measurements

- scenarios: 8;
- matching dual-oracle joins: 1;
- adversarial holds: 7;
- oracle receipts joined: 2;
- record or detached-digest mismatch acceptances: 0;
- incomplete-verdict acceptances: 0;
- authority escalations: 0;
- accepted Recovery Coverage Matrix: 8/8, zero gaps;
- inherited shared-cooling lead: 27 samples (19 versus 46);
- deployment, runtime write, network, storage, and hardware actions: 0.

## Licensing and provenance

The join and its schemas are original MIT-licensed TruePanel code. No in-toto,
SLSA, or Sigstore code or schema is embedded. Existing Bouncy Castle and DSS
libraries remain pinned development/CI dependencies behind TruePanel-owned
adapters; neither enters the appliance wheel. Source links and decisions are
preserved above for attribution and later review.

## Strongest next step

Define authenticated custody for a real active EvidenceRecord, then issue the
two validators' receipts over those exact bytes and bind the aggregate to the
reviewed time, revocation, and policy envelope. Until that exists, the active
runtime record must remain `PENDING` and no recovery gains operational trust.
