# AEGIS OCSP evidence package

## Outcome

AEGIS now verifies an exact signed DER OCSP response for the governed timestamp-
authority certificate, requires a `GOOD` status for that exact certificate serial, and
requires a verified RFC 3161 archive timestamp over the canonical evidence manifest
before the response's `nextUpdate`. The manifest binds the TSA, issuer, delegated
responder, OCSP response, status, responder identity, `producedAt`, `thisUpdate`, and
`nextUpdate` by content identity rather than by caller-supplied summaries or URLs.

The replaceable adapter invokes the installed OpenSSL executable with fixed arguments,
bounded memory-backed inputs, a timeout, no shell, and no network. `-no_intern` prevents
an embedded certificate from silently becoming the responder identity;
`-verify_other` supplies the one responder certificate whose direct issuer chain and
`id-kp-OCSPSigning` authorization OpenSSL must verify. The package grants timestamp-
rotation evidence eligibility only. Validation, installation, deployment, capture,
runtime, storage, network, and hardware authority remain false.

## HoloDeck evidence

Nine deterministic paths trust one authorized `GOOD` response archived before expiry
and hold a revoked status, unauthorized signer, wrong certificate ID, missing
`nextUpdate`, tampered response, missing archive timestamp, timestamp over different
bytes, and authority escalation. The fixture creates real CA, TSA, delegated OCSP
responder, unauthorized signer, and timestamp certificates; five DER OCSP responses;
and an RFC 3161 token in an isolated temporary directory. Seven private keys are
created and none retained.

Recovery coverage remains 8/8. Shared cooling appears at sample 19 versus isolated
thresholds at sample 46, a 27-sample lead at 0.95 evidence-weight confidence.

Evidence: `docs/evidence/aegis-temperature-ocsp-evidence-package-v1.json`

## Prior-Art Field Report

| Candidate | What was inspected | Capability, fit, and maturity | Dependency / security / license | Decision |
| --- | --- | --- | --- | --- |
| RFC 6960 | `BasicOCSPResponse`, `CertID`, delegated signer authorization, `producedAt`, `thisUpdate`, and `nextUpdate` | Normative definition of the certificate-status and responder-custody checks needed here | Standard; no code or attribution obligation | **Adopt semantics.** |
| OpenSSL 3 OCSP | Response parsing and signature verification, `-verify_other`, `-no_intern`, chain/EKU checks, and validity controls | Mature, already required by TruePanel, and able to verify real fixtures without adding a service or parser dependency | Installed executable, Apache-2.0; fixed argv, no shell or network; intentionally excludes `-noverify`, `-no_cert_checks`, and `-trust_other` | **Adopt behind a TruePanel-owned interface.** |
| ETSI DSS `OnlineOCSPSource` and validation levels | Nonce/freshness handling, mandatory `nextUpdate` policy, validation-material preservation | Strong long-term-validation architecture, but its Java validation stack and network source model are too large for this local evidence gate | LGPL-2.1; no code copied or linked | **Architectural reference only.** |
| PyCA cryptography OCSP API/tests | Typed request/response builders, `GOOD` fixtures, responder ID, and update-time coverage | Mature, well-tested replacement candidate; unnecessary weight while the already-required OpenSSL boundary performs the complete verification | Apache-2.0 OR BSD-3-Clause; notice obligations if distributed | **Keep as replacement candidate; do not add yet.** |
| Sigstore/Cosign timestamp verification | RFC 3161 verification path and stated CRL/OCSP limitation | Strong supply-chain ecosystem fit, but current generic timestamp verification does not provide this responder/status path | Apache-2.0; no code copied | **Collaboration target; contribute policy lessons rather than importing behavior.** |
| RFC 4998 evidence records | Archive timestamp and renewal model for CRL/OCSP material | Best model for the next combined CRL+OCSP renewal chain; full ASN.1 ERS remains disproportionate now | Standard; concepts only | **Adapt the renewal invariant next.** |

Sources inspected 2026-11-10: [RFC 6960](https://www.rfc-editor.org/rfc/rfc6960.html),
[OpenSSL OCSP](https://docs.openssl.org/master/man1/openssl-ocsp/),
[ETSI DSS OCSP source](https://ec.europa.eu/digital-building-blocks/DSS/webapp-demo/apidocs/eu/europa/esig/dss/service/http/commons/OnlineOCSPSource.html),
[ETSI DSS](https://github.com/esig/dss),
[PyCA OCSP tests](https://github.com/pyca/cryptography/blob/main/tests/x509/test_ocsp.py),
[PyCA license](https://github.com/pyca/cryptography/blob/main/LICENSE),
[Sigstore verification](https://github.com/sigstore/cosign/blob/main/pkg/cosign/verify.go), and
[RFC 4998](https://www.rfc-editor.org/rfc/rfc4998.html).

## Provenance, rejected paths, and risks

No external source code, schema, dependency, service, credential, key, certificate,
OCSP response, or dataset was copied. OpenSSL remains an independently replaceable
execution boundary behind TruePanel's inspector. Every cryptographic fixture is
generated locally and every private key is confined to a temporary directory.

Rejected: `-noverify`, `-no_cert_checks`, or `-trust_other`; trusting an embedded
responder without an explicitly supplied identity; accepting `GOOD` without an exact
certificate ID; accepting a response without `nextUpdate`; substituting a URL or parsed
summary for DER bytes; fetching over the network during evaluation; adding PyCA solely
for parsing; and allowing evidence eligibility to imply trust-bundle activation.

This proves a deterministic delegated-responder path, not real CA publication
freshness, nonce behavior for online requests, human operator independence, or
long-term algorithm migration. The strongest next step is one combined CRL+OCSP
archive-renewal chain that renews before either evidence object, timestamp certificate,
or digest policy becomes unsuitable. OpenSSL, Sigstore, and ETSI DSS maintainers are
the most promising collaboration targets.
