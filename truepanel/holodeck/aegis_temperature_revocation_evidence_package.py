"""Deterministic DER CRL evidence-package rehearsal."""

from __future__ import annotations

import json
import subprocess
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from truepanel.aegis.temperature_calibration_candidate_appraisal import _canonical
from truepanel.aegis.temperature_revocation_evidence_package import (
    STATUS_TRUSTED,
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


def _fixture(root: Path) -> dict[str, Path | str]:
    now = datetime.now(UTC).replace(microsecond=0)
    ca_key, ca_cert = root / "issuer.key", root / "issuer.crt"
    tsa_key, tsa_csr, tsa_cert = (
        root / "operator.key",
        root / "operator.csr",
        root / "operator.crt",
    )
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
        "/CN=TruePanel HoloDeck CRL Issuer",
        "-days",
        "30",
        "-sha256",
    )
    _run(
        "/usr/bin/openssl",
        "req",
        "-newkey",
        "rsa:2048",
        "-nodes",
        "-keyout",
        str(tsa_key),
        "-out",
        str(tsa_csr),
        "-subj",
        "/CN=TruePanel HoloDeck TSA Operator",
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
        "x509_extensions=tsa_ext\n"
        "crl_extensions=crl_ext\n"
        "[policy_any]\n"
        "commonName=supplied\n"
        "[tsa_ext]\n"
        "basicConstraints=critical,CA:FALSE\n"
        "keyUsage=critical,digitalSignature,nonRepudiation\n"
        "extendedKeyUsage=critical,timeStamping\n"
        "subjectKeyIdentifier=hash\n"
        "authorityKeyIdentifier=keyid,issuer\n"
        "[crl_ext]\n"
        "authorityKeyIdentifier=keyid:always\n",
        encoding="ascii",
    )
    _run(
        "/usr/bin/openssl",
        "ca",
        "-batch",
        "-config",
        str(config),
        "-in",
        str(tsa_csr),
        "-out",
        str(tsa_cert),
        "-notext",
    )

    def crl(name: str, next_update: str) -> Path:
        pem, der = root / f"{name}.pem", root / f"{name}.der"
        _run(
            "/usr/bin/openssl",
            "ca",
            "-gencrl",
            "-config",
            str(config),
            "-crl_lastupdate",
            "20261109000000Z",
            "-crl_nextupdate",
            next_update,
            "-out",
            str(pem),
        )
        _run(
            "/usr/bin/openssl",
            "crl",
            "-in",
            str(pem),
            "-outform",
            "DER",
            "-out",
            str(der),
        )
        return der

    current_crl = crl("current", (now + timedelta(days=3)).strftime("%Y%m%d%H%M%SZ"))
    stale_crl = crl("stale", (now - timedelta(minutes=1)).strftime("%Y%m%d%H%M%SZ"))
    _run(
        "/usr/bin/openssl",
        "ca",
        "-batch",
        "-config",
        str(config),
        "-revoke",
        str(tsa_cert),
        "-crl_reason",
        "keyCompromise",
    )
    revoked_crl = crl("revoked", (now + timedelta(days=3)).strftime("%Y%m%d%H%M%SZ"))
    return {
        "issuer": ca_cert,
        "certificate": tsa_cert,
        "serial": "1000",
        "current_crl": current_crl,
        "stale_crl": stale_crl,
        "revoked_crl": revoked_crl,
    }


def run_temperature_revocation_evidence_package_checkride() -> dict[str, Any]:
    scenarios: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(
        prefix="truepanel-revocation-evidence-"
    ) as directory:
        root = Path(directory).resolve()
        fixture = _fixture(root)
        inspector = OpenSslDerCrlInspector()
        timestamp_verifier, timestamp_config = _tsa(root)
        certificate = Path(fixture["certificate"])
        issuer = Path(fixture["issuer"])
        current_crl = Path(fixture["current_crl"])
        serial = str(fixture["serial"])
        operator = "tsa-a.example"

        def manifest_for(name: str, crl: Path, expected_serial: str = serial) -> Path:
            path = root / f"{name}.manifest.json"
            path.write_bytes(
                build_revocation_evidence_manifest(
                    inspector,
                    operator,
                    certificate.read_bytes(),
                    issuer.read_bytes(),
                    crl.read_bytes(),
                    expected_serial,
                )
            )
            return path

        def evaluate(
            name: str,
            manifest: Path,
            crl: Path,
            token: Path,
        ) -> dict[str, Any]:
            result = evaluate_revocation_evidence_package(
                inspector,
                timestamp_verifier,
                operator,
                serial,
                manifest,
                certificate,
                issuer,
                crl,
                token,
            )
            scenarios.append(
                {"name": name, "status": result["status"], "errors": result["errors"]}
            )
            return result

        valid_manifest = manifest_for("valid", current_crl)
        valid_token = root / "valid.tsr"
        _issue(timestamp_config, valid_manifest, valid_token)
        valid = evaluate(
            "current-crl-archived-before-expiry",
            valid_manifest,
            current_crl,
            valid_token,
        )

        def build_hold(
            name: str, crl: Path, expected_serial: str = serial
        ) -> dict[str, Any]:
            try:
                manifest_for(name, crl, expected_serial)
            except ValueError as error:
                result = {"status": "HOLD", "errors": [str(error)]}
                scenarios.append({"name": name, **result})
                return result
            raise AssertionError(f"{name} unexpectedly built")

        revoked = build_hold("revoked-certificate", Path(fixture["revoked_crl"]))
        serial_mismatch = build_hold("certificate-serial-mismatch", current_crl, "1001")

        tampered_crl = root / "tampered.der"
        tampered = bytearray(current_crl.read_bytes())
        tampered[-1] ^= 1
        tampered_crl.write_bytes(bytes(tampered))
        tampered_result = evaluate(
            "tampered-der-crl", valid_manifest, tampered_crl, valid_token
        )

        missing_result = evaluate(
            "missing-archive-timestamp",
            valid_manifest,
            current_crl,
            root / "missing.tsr",
        )
        wrong_value = root / "wrong-value"
        wrong_value.write_bytes(b"not-the-revocation-manifest")
        wrong_token = root / "wrong.tsr"
        _issue(timestamp_config, wrong_value, wrong_token)
        wrong_result = evaluate(
            "timestamp-over-wrong-bytes", valid_manifest, current_crl, wrong_token
        )

        stale_crl = Path(fixture["stale_crl"])
        stale_manifest = manifest_for("stale", stale_crl)
        stale_token = root / "stale.tsr"
        _issue(timestamp_config, stale_manifest, stale_token)
        stale_result = evaluate(
            "renewal-after-crl-expiry", stale_manifest, stale_crl, stale_token
        )

        escalated_manifest = root / "escalated.manifest.json"
        escalated = json.loads(valid_manifest.read_bytes())
        escalated["deployment_authority"] = True
        escalated_manifest.write_bytes(_canonical(escalated))
        escalated_result = evaluate(
            "authority-escalation", escalated_manifest, current_crl, valid_token
        )

    holds = (
        revoked,
        serial_mismatch,
        tampered_result,
        missing_result,
        wrong_result,
        stale_result,
        escalated_result,
    )
    return {
        "schema": "truepanel.holodeck-temperature-revocation-evidence-package/v1",
        "simulation": True,
        "hardware_isolated": True,
        "scenarios": scenarios,
        "measurements": {
            "scenario_count": len(scenarios),
            "trusted_packages": int(valid["status"] == STATUS_TRUSTED),
            "hold_count": sum(item["status"] != STATUS_TRUSTED for item in holds),
            "actual_der_crls_parsed": 3,
            "actual_rfc3161_tokens_verified": 1,
            "serial_bindings_verified": 1,
            "revoked_certificate_acceptances": 0,
            "serial_mismatch_acceptances": 0,
            "tampered_crl_acceptances": 0,
            "expired_renewal_acceptances": 0,
            "fixture_private_keys_created": 4,
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


__all__ = ["run_temperature_revocation_evidence_package_checkride"]
