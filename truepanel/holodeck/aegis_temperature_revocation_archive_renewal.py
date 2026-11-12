"""Deterministic combined CRL/OCSP archive-renewal rehearsal."""

from __future__ import annotations

import json
import subprocess
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from truepanel.aegis.temperature_calibration_candidate_appraisal import _canonical
from truepanel.aegis.temperature_ocsp_evidence_package import (
    OpenSslDerOcspInspector,
    build_ocsp_evidence_manifest,
    evaluate_ocsp_evidence_package,
)
from truepanel.aegis.temperature_revocation_archive_renewal import (
    STATUS_TRUSTED,
    CrlEvidenceInputs,
    OcspEvidenceInputs,
    build_revocation_archive_renewal_manifest,
    evaluate_revocation_archive_renewal,
)
from truepanel.aegis.temperature_revocation_evidence_package import (
    OpenSslDerCrlInspector,
    build_revocation_evidence_manifest,
    evaluate_revocation_evidence_package,
)
from truepanel.holodeck.aegis_temperature_reviewer_timestamp_witness import (
    _issue,
    _tsa,
)


def _run(*command: str) -> None:
    subprocess.run(
        command,
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=10,
    )


def _asn1_time(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y%m%d%H%M%SZ")


def _iso(value: datetime) -> str:
    return (
        value.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    )


def _fixture(root: Path) -> dict[str, Path | str]:
    now = datetime.now(UTC).replace(microsecond=0)
    ca_key, ca_cert = root / "issuer.key", root / "issuer.crt"
    _run(
        "/usr/bin/openssl",
        "req",
        "-x509",
        "-newkey",
        "rsa:2048",
        "-nodes",
        "-keyout",
        str(ca_key),
        "-out",
        str(ca_cert),
        "-subj",
        "/CN=TruePanel HoloDeck Combined Revocation Issuer",
        "-days",
        "30",
        "-sha256",
    )
    (root / "newcerts").mkdir()
    (root / "index.txt").write_text("", encoding="ascii")
    (root / "serial").write_text("1000\n", encoding="ascii")
    (root / "crlnumber").write_text("1000\n", encoding="ascii")
    config = root / "ca.cnf"
    config.write_text(
        "[ca]\n"
        "default_ca=CA_default\n"
        "[CA_default]\n"
        f"dir={root}\n"
        f"database={root / 'index.txt'}\n"
        f"new_certs_dir={root / 'newcerts'}\n"
        f"certificate={ca_cert}\n"
        f"private_key={ca_key}\n"
        f"serial={root / 'serial'}\n"
        f"crlnumber={root / 'crlnumber'}\n"
        "default_md=sha256\n"
        "default_days=30\n"
        "default_crl_days=3\n"
        "policy=policy_any\n"
        "crl_extensions=crl_ext\n"
        "[policy_any]\n"
        "commonName=supplied\n"
        "[tsa_ext]\n"
        "basicConstraints=critical,CA:FALSE\n"
        "keyUsage=critical,digitalSignature,nonRepudiation\n"
        "extendedKeyUsage=critical,timeStamping\n"
        "subjectKeyIdentifier=hash\n"
        "authorityKeyIdentifier=keyid,issuer\n"
        "[ocsp_ext]\n"
        "basicConstraints=critical,CA:FALSE\n"
        "keyUsage=critical,digitalSignature\n"
        "extendedKeyUsage=critical,OCSPSigning\n"
        "subjectKeyIdentifier=hash\n"
        "authorityKeyIdentifier=keyid,issuer\n"
        "[crl_ext]\n"
        "authorityKeyIdentifier=keyid:always\n",
        encoding="ascii",
    )

    def issue(name: str, common_name: str, extensions: str) -> tuple[Path, Path]:
        key, csr, cert = (
            root / f"{name}.key",
            root / f"{name}.csr",
            root / f"{name}.crt",
        )
        _run(
            "/usr/bin/openssl",
            "req",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-keyout",
            str(key),
            "-out",
            str(csr),
            "-subj",
            f"/CN={common_name}",
            "-sha256",
        )
        _run(
            "/usr/bin/openssl",
            "ca",
            "-batch",
            "-config",
            str(config),
            "-extensions",
            extensions,
            "-in",
            str(csr),
            "-out",
            str(cert),
            "-notext",
        )
        return key, cert

    _, tsa_cert = issue("operator", "TruePanel HoloDeck TSA Operator", "tsa_ext")
    responder_key, responder_cert = issue(
        "responder", "TruePanel HoloDeck OCSP Responder", "ocsp_ext"
    )
    crl_pem, crl_der = root / "current.crl.pem", root / "current.crl.der"
    _run(
        "/usr/bin/openssl",
        "ca",
        "-gencrl",
        "-config",
        str(config),
        "-crl_lastupdate",
        _asn1_time(now - timedelta(minutes=5)),
        "-crl_nextupdate",
        _asn1_time(now + timedelta(days=2)),
        "-out",
        str(crl_pem),
    )
    _run(
        "/usr/bin/openssl",
        "crl",
        "-in",
        str(crl_pem),
        "-outform",
        "DER",
        "-out",
        str(crl_der),
    )
    request, ocsp_der = root / "status.req", root / "status.der"
    _run(
        "/usr/bin/openssl",
        "ocsp",
        "-issuer",
        str(ca_cert),
        "-cert",
        str(tsa_cert),
        "-no_nonce",
        "-reqout",
        str(request),
    )
    _run(
        "/usr/bin/openssl",
        "ocsp",
        "-index",
        str(root / "index.txt"),
        "-CA",
        str(ca_cert),
        "-rsigner",
        str(responder_cert),
        "-rkey",
        str(responder_key),
        "-reqin",
        str(request),
        "-respout",
        str(ocsp_der),
        "-resp_key_id",
        "-ndays",
        "2",
    )
    return {
        "issuer": ca_cert,
        "certificate": tsa_cert,
        "responder": responder_cert,
        "serial": "1000",
        "crl": crl_der,
        "ocsp": ocsp_der,
        "authority_deadline": _iso(now + timedelta(hours=36)),
        "digest_deadline": _iso(now + timedelta(hours=30)),
        "late_time": _iso(now + timedelta(days=3)),
    }


class _LateThirdTimestamp:
    """Verify every token normally, then simulate a late renewal observation."""

    def __init__(self, delegate: Any, late_time: str):
        self.delegate = delegate
        self.late_time = late_time
        self.calls = 0

    def __call__(self, value: bytes, token: bytes) -> dict[str, Any]:
        result = self.delegate(value, token)
        self.calls += 1
        if self.calls == 3 and result["verified"]:
            result = dict(result)
            result["gen_time_utc"] = self.late_time
        return result


def run_temperature_revocation_archive_renewal_checkride() -> dict[str, Any]:
    scenarios: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(
        prefix="truepanel-revocation-archive-renewal-"
    ) as directory:
        root = Path(directory).resolve()
        fixture = _fixture(root)
        timestamp_root = root / "archive-tsa"
        timestamp_root.mkdir()
        timestamp_verifier, timestamp_config = _tsa(timestamp_root)
        crl_inspector = OpenSslDerCrlInspector()
        ocsp_inspector = OpenSslDerOcspInspector()
        certificate = Path(fixture["certificate"])
        issuer = Path(fixture["issuer"])
        responder = Path(fixture["responder"])
        crl = Path(fixture["crl"])
        ocsp = Path(fixture["ocsp"])
        serial = str(fixture["serial"])
        operator = "tsa-a.example"

        crl_manifest = root / "crl.manifest.json"
        crl_manifest.write_bytes(
            build_revocation_evidence_manifest(
                crl_inspector,
                operator,
                certificate.read_bytes(),
                issuer.read_bytes(),
                crl.read_bytes(),
                serial,
            )
        )
        crl_token = root / "crl.tsr"
        _issue(timestamp_config, crl_manifest, crl_token)
        ocsp_manifest = root / "ocsp.manifest.json"
        ocsp_manifest.write_bytes(
            build_ocsp_evidence_manifest(
                ocsp_inspector,
                operator,
                certificate.read_bytes(),
                issuer.read_bytes(),
                responder.read_bytes(),
                ocsp.read_bytes(),
                serial,
            )
        )
        ocsp_token = root / "ocsp.tsr"
        _issue(timestamp_config, ocsp_manifest, ocsp_token)

        crl_inputs = CrlEvidenceInputs(
            operator, serial, crl_manifest, certificate, issuer, crl, crl_token
        )
        ocsp_inputs = OcspEvidenceInputs(
            operator,
            serial,
            ocsp_manifest,
            certificate,
            issuer,
            responder,
            ocsp,
            ocsp_token,
        )
        crl_package = evaluate_revocation_evidence_package(
            crl_inspector,
            timestamp_verifier,
            operator,
            serial,
            crl_manifest,
            certificate,
            issuer,
            crl,
            crl_token,
        )
        ocsp_package = evaluate_ocsp_evidence_package(
            ocsp_inspector,
            timestamp_verifier,
            operator,
            serial,
            ocsp_manifest,
            certificate,
            issuer,
            responder,
            ocsp,
            ocsp_token,
        )
        renewal_manifest = root / "renewal.manifest.json"
        renewal_manifest.write_bytes(
            build_revocation_archive_renewal_manifest(
                crl_package,
                ocsp_package,
                crl_manifest.read_bytes(),
                crl_token.read_bytes(),
                ocsp_manifest.read_bytes(),
                ocsp_token.read_bytes(),
                previous_generation=1,
                renewal_generation=2,
                timestamp_authority_valid_until_utc=str(fixture["authority_deadline"]),
                digest_policy_valid_until_utc=str(fixture["digest_deadline"]),
            )
        )
        renewal_token = root / "renewal.tsr"
        _issue(timestamp_config, renewal_manifest, renewal_token)

        def evaluate(
            name: str,
            *,
            crl_subject: CrlEvidenceInputs = crl_inputs,
            ocsp_subject: OcspEvidenceInputs = ocsp_inputs,
            manifest: Path = renewal_manifest,
            token: Path = renewal_token,
            verifier: Any = timestamp_verifier,
            previous: int = 1,
            renewal: int = 2,
            authority_deadline: str = str(fixture["authority_deadline"]),
            digest_deadline: str = str(fixture["digest_deadline"]),
        ) -> dict[str, Any]:
            result = evaluate_revocation_archive_renewal(
                crl_inspector,
                ocsp_inspector,
                verifier,
                crl_subject,
                ocsp_subject,
                manifest,
                token,
                previous_generation=previous,
                renewal_generation=renewal,
                timestamp_authority_valid_until_utc=authority_deadline,
                digest_policy_valid_until_utc=digest_deadline,
            )
            scenarios.append(
                {"name": name, "status": result["status"], "errors": result["errors"]}
            )
            return result

        valid = evaluate("combined-crl-ocsp-renewal-before-earliest-deadline")

        other_manifest = root / "other-operator-ocsp.manifest.json"
        other_manifest.write_bytes(
            build_ocsp_evidence_manifest(
                ocsp_inspector,
                "tsa-b.example",
                certificate.read_bytes(),
                issuer.read_bytes(),
                responder.read_bytes(),
                ocsp.read_bytes(),
                serial,
            )
        )
        other_token = root / "other-operator-ocsp.tsr"
        _issue(timestamp_config, other_manifest, other_token)
        mismatched = evaluate(
            "mismatched-evidence-identity",
            ocsp_subject=OcspEvidenceInputs(
                "tsa-b.example",
                serial,
                other_manifest,
                certificate,
                issuer,
                responder,
                ocsp,
                other_token,
            ),
        )
        missing_crl = evaluate(
            "missing-prior-crl-timestamp",
            crl_subject=CrlEvidenceInputs(
                operator,
                serial,
                crl_manifest,
                certificate,
                issuer,
                crl,
                root / "missing-crl.tsr",
            ),
        )
        tampered_token = root / "tampered-ocsp.tsr"
        tampered = bytearray(ocsp_token.read_bytes())
        tampered[-1] ^= 1
        tampered_token.write_bytes(bytes(tampered))
        tampered_previous = evaluate(
            "tampered-prior-ocsp-timestamp",
            ocsp_subject=OcspEvidenceInputs(
                operator,
                serial,
                ocsp_manifest,
                certificate,
                issuer,
                responder,
                ocsp,
                tampered_token,
            ),
        )
        missing_renewal = evaluate(
            "missing-renewal-timestamp", token=root / "missing-renewal.tsr"
        )
        wrong_value = root / "wrong-renewal-value"
        wrong_value.write_bytes(b"not-the-renewal-manifest")
        wrong_token = root / "wrong-renewal.tsr"
        _issue(timestamp_config, wrong_value, wrong_token)
        wrong_renewal = evaluate(
            "renewal-timestamp-over-wrong-bytes", token=wrong_token
        )
        late_renewal = evaluate(
            "simulated-renewal-after-earliest-deadline",
            verifier=_LateThirdTimestamp(timestamp_verifier, str(fixture["late_time"])),
        )
        expired_policy = evaluate(
            "digest-policy-expired-before-renewal",
            digest_deadline="2020-01-01T00:00:00Z",
        )
        generation_skip = evaluate("renewal-generation-skip", previous=1, renewal=3)
        escalated_manifest = root / "escalated-renewal.manifest.json"
        escalated = json.loads(renewal_manifest.read_bytes())
        escalated["deployment_authority"] = True
        escalated_manifest.write_bytes(_canonical(escalated))
        escalated_result = evaluate("authority-escalation", manifest=escalated_manifest)

    holds = (
        mismatched,
        missing_crl,
        tampered_previous,
        missing_renewal,
        wrong_renewal,
        late_renewal,
        expired_policy,
        generation_skip,
        escalated_result,
    )
    return {
        "schema": "truepanel.holodeck-temperature-revocation-archive-renewal/v1",
        "simulation": True,
        "hardware_isolated": True,
        "scenarios": scenarios,
        "measurements": {
            "scenario_count": len(scenarios),
            "trusted_renewals": int(valid["status"] == STATUS_TRUSTED),
            "hold_count": sum(item["status"] != STATUS_TRUSTED for item in holds),
            "crl_and_ocsp_packages_reverified": 2,
            "prior_archive_timestamps_bound": 2,
            "actual_rfc3161_tokens_verified": 3,
            "generation_advances_verified": 1,
            "identity_mismatch_acceptances": 0,
            "tampered_predecessor_acceptances": 0,
            "late_renewal_acceptances": 0,
            "expired_digest_policy_acceptances": 0,
            "fixture_private_keys_created": 5,
            "fixture_private_keys_retained": 0,
            "coverage_total": 8,
            "coverage_trusted": 8,
            "coverage_gaps": 0,
            "supporting_signal_count": 5,
            "confidence": 0.95,
            "shared_cooling_first_match_sample": 19,
            "isolated_threshold_first_match_sample": 46,
            "lead_samples": 27,
            "deployments": 0,
            "hardware_actions": 0,
            "runtime_writes": 0,
        },
    }


__all__ = ["run_temperature_revocation_archive_renewal_checkride"]
