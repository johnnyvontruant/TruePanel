# AEGIS revocation evidence package

## Outcome

AEGIS now verifies the exact DER CRL used to support a timestamp-authority rotation,
binds it to the governed TSA certificate serial and issuer, and requires a verified RFC
3161 archive timestamp over the canonical manifest before the CRL expires. The package
records the exact CRL, TSA certificate, issuer certificate, and manifest digests. A URL,
parsed summary, post-expiry renewal, or caller-asserted serial cannot substitute for the
signed objects.

The adapter invokes the installed OpenSSL executable with fixed arguments, bounded
memory-backed inputs, timeouts, signature verification, and no shell. It grants rotation
evidence eligibility only; validation, installation, deployment, capture, runtime,
storage, network, and hardware authority remain false.

## HoloDeck evidence

Eight deterministic paths trust one current, correctly signed DER CRL archived before
expiry and hold a revoked TSA certificate, certificate-serial mismatch, tampered CRL,
missing archive timestamp, timestamp over different bytes, post-expiry renewal, and
authority escalation. The fixture creates real CA/TSA certificates, three DER CRLs, and
RFC 3161 tokens in an isolated temporary directory; four private keys are deleted.

Recovery coverage remains 8/8. Shared cooling appears at sample 19 versus isolated
thresholds at sample 46, a 27-sample lead at 0.95 evidence-weight confidence.

Evidence: `docs/evidence/aegis-temperature-revocation-evidence-package-v1.json`

## Prior-Art Field Report

| Candidate | What was inspected | Capability, fit, and maturity | Dependency / security / license | Decision |
| --- | --- | --- | --- | --- |
| RFC 5280 CRL profile | DER `CertificateList`, issuer, `thisUpdate`, `nextUpdate`, revoked certificate serials | Normative and directly maps the required evidence identity and freshness checks | Standard; no code or attribution obligation | **Adopt semantics.** |
| RFC 6960 OCSP | Signed response status, `producedAt`, `thisUpdate`, `nextUpdate`, certificate ID | Normative and valuable, but responder authorization and chain verification need a separate complete fixture | Standard; no code copied | **Defer until equivalent signer and responder checks are rehearsed.** |
| RFC 4998 ERS | Archive timestamps, renewal before algorithm/certificate weakness, preserved CRL/OCSP material | Best architectural match for durable evidence; full ASN.1 ERS is too heavy for this increment | Standard; concepts only | **Adapt one-object archive renewal now; evaluate full ERS later.** |
| OpenSSL 3 CRL/RFC 3161 tools | DER parsing, CRL signature verification, certificate-chain verification, timestamp verification | Already required by TruePanel and exercised by existing timestamp code; mature and replaceable | Installed executable, Apache-2.0; fixed argv, no shell or network | **Adopt behind a TruePanel interface.** |
| PyCA cryptography | `load_der_x509_crl`, OCSP response parsing, test vectors | Excellent typed API and test quality, but adds a compiled Rust/OpenSSL dependency solely for parsing | Apache-2.0 OR BSD-3-Clause; notice obligations if distributed | **Do not add yet; reconsider when OCSP support justifies the weight.** |
| Sigstore timestamp verification | RFC 3161 verification and trust-root distribution | Strong ecosystem fit, but current Cosign verification explicitly does not perform CRL/OCSP checks | Apache-2.0; no code copied | **Collaborate and borrow policy lessons, not behavior.** |
| ETSI DSS | Long-term signature validation and validation-material archive model | Broad and mature, but a JVM/XML validation stack is disproportionate for a NAS control plane | Apache-2.0; large dependency and operational surface | **Architectural reference only.** |

Sources inspected 2026-11-09: [RFC 5280](https://www.rfc-editor.org/rfc/rfc5280.html),
[RFC 6960](https://www.rfc-editor.org/rfc/rfc6960.html),
[RFC 4998](https://www.rfc-editor.org/rfc/rfc4998.html),
[OpenSSL CRL](https://docs.openssl.org/3.0/man1/openssl-crl/),
[OpenSSL OCSP](https://docs.openssl.org/master/man1/openssl-ocsp/),
[PyCA X.509](https://cryptography.io/en/latest/x509/reference/),
[PyCA license](https://github.com/pyca/cryptography/blob/main/LICENSE),
[Sigstore verification](https://github.com/sigstore/cosign/blob/main/pkg/cosign/verify.go), and
[ETSI DSS](https://github.com/esig/dss).

## Provenance, rejected paths, and risks

No external source, schema, dependency, service, credential, key, certificate, CRL,
OCSP response, or dataset was copied. OpenSSL remains an independently replaceable
execution boundary. The new fixture generates all cryptographic material locally and
retains no private key.

Rejected: trusting CRL metadata without signature verification; accepting a CRL URL as
evidence; comparing an unverified caller serial; treating CRL absence as proof without
issuer validation; accepting a timestamp created after `nextUpdate`; adding PyCA solely
to parse one object; accepting OCSP before responder authorization is fully verified;
and automatically activating a rotated trust bundle.

This proves a complete CRL path, not OCSP responder custody, real CA publication
freshness, human governance independence, or long-term algorithm migration. The
strongest next step is an equivalent signed OCSP package that verifies responder
authorization and certificate ID, followed by a two-object renewal chain before either
the archive timestamp certificate or digest algorithm becomes unsuitable. Sigstore,
OpenSSL, and ETSI DSS maintainers are the most promising collaboration targets.
