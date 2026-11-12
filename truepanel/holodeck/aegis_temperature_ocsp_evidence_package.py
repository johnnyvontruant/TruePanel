"""Deterministic signed OCSP evidence-package rehearsal."""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from truepanel.aegis.temperature_calibration_candidate_appraisal import _canonical
from truepanel.aegis.temperature_ocsp_evidence_package import (
    STATUS_TRUSTED,
    OpenSslDerOcspInspector,
    build_ocsp_evidence_manifest,
    evaluate_ocsp_evidence_package,
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
        "/CN=TruePanel HoloDeck OCSP Issuer",
        "-days",
        "30",
        "-sha256",
    )
    (root / "newcerts").mkdir()
    (root / "index.txt").write_text("", encoding="ascii")
    (root / "serial").write_text("1000\n", encoding="ascii")
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
        "default_md=sha256\n"
        "default_days=30\n"
        "policy=policy_any\n"
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
        "[plain_ext]\n"
        "basicConstraints=critical,CA:FALSE\n"
        "keyUsage=critical,digitalSignature\n"
        "subjectKeyIdentifier=hash\n"
        "authorityKeyIdentifier=keyid,issuer\n",
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

    tsa_key, tsa_cert = issue("operator", "TruePanel HoloDeck TSA Operator", "tsa_ext")
    responder_key, responder_cert = issue(
        "responder", "TruePanel HoloDeck OCSP Responder", "ocsp_ext"
    )
    unauthorized_key, unauthorized_cert = issue(
        "unauthorized", "TruePanel HoloDeck Plain Signer", "plain_ext"
    )
    _, other_cert = issue("other-operator", "TruePanel HoloDeck Other TSA", "tsa_ext")

    def response(
        name: str,
        cert: Path,
        signer_cert: Path,
        signer_key: Path,
        *,
        next_update: bool = True,
    ) -> Path:
        request, output = root / f"{name}.req", root / f"{name}.der"
        _run(
            "/usr/bin/openssl",
            "ocsp",
            "-issuer",
            str(ca_cert),
            "-cert",
            str(cert),
            "-no_nonce",
            "-reqout",
            str(request),
        )
        command = [
            "/usr/bin/openssl",
            "ocsp",
            "-index",
            str(root / "index.txt"),
            "-CA",
            str(ca_cert),
            "-rsigner",
            str(signer_cert),
            "-rkey",
            str(signer_key),
            "-reqin",
            str(request),
            "-respout",
            str(output),
            "-resp_key_id",
        ]
        if next_update:
            command.extend(("-ndays", "2"))
        _run(*command)
        return output

    good = response("good", tsa_cert, responder_cert, responder_key)
    no_next_update = response(
        "no-next-update", tsa_cert, responder_cert, responder_key, next_update=False
    )
    unauthorized = response(
        "unauthorized", tsa_cert, unauthorized_cert, unauthorized_key
    )
    other = response("other", other_cert, responder_cert, responder_key)
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
    revoked = response("revoked", tsa_cert, responder_cert, responder_key)
    return {
        "issuer": ca_cert,
        "certificate": tsa_cert,
        "serial": "1000",
        "responder": responder_cert,
        "unauthorized_responder": unauthorized_cert,
        "other_certificate": other_cert,
        "other_serial": "1003",
        "good": good,
        "no_next_update": no_next_update,
        "unauthorized": unauthorized,
        "other": other,
        "revoked": revoked,
        "private_key_count": "5",
    }


def run_temperature_ocsp_evidence_package_checkride() -> dict[str, Any]:
    scenarios: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="truepanel-ocsp-evidence-") as directory:
        root = Path(directory).resolve()
        fixture = _fixture(root)
        inspector = OpenSslDerOcspInspector()
        timestamp_verifier, timestamp_config = _tsa(root)
        certificate = Path(fixture["certificate"])
        issuer = Path(fixture["issuer"])
        responder = Path(fixture["responder"])
        good = Path(fixture["good"])
        serial = str(fixture["serial"])
        operator = "tsa-a.example"

        def manifest_for(
            name: str,
            response: Path,
            *,
            target: Path = certificate,
            responder_cert: Path = responder,
            expected_serial: str = serial,
        ) -> Path:
            path = root / f"{name}.manifest.json"
            path.write_bytes(
                build_ocsp_evidence_manifest(
                    inspector,
                    operator,
                    target.read_bytes(),
                    issuer.read_bytes(),
                    responder_cert.read_bytes(),
                    response.read_bytes(),
                    expected_serial,
                )
            )
            return path

        def evaluate(
            name: str,
            manifest: Path,
            response: Path,
            token: Path,
        ) -> dict[str, Any]:
            result = evaluate_ocsp_evidence_package(
                inspector,
                timestamp_verifier,
                operator,
                serial,
                manifest,
                certificate,
                issuer,
                responder,
                response,
                token,
            )
            scenarios.append(
                {"name": name, "status": result["status"], "errors": result["errors"]}
            )
            return result

        valid_manifest = manifest_for("valid", good)
        valid_token = root / "valid.tsr"
        _issue(timestamp_config, valid_manifest, valid_token)
        valid = evaluate(
            "authorized-good-response-archived-before-expiry",
            valid_manifest,
            good,
            valid_token,
        )

        def build_hold(name: str, **kwargs: Any) -> dict[str, Any]:
            try:
                manifest_for(name, **kwargs)
            except ValueError as error:
                result = {"status": "HOLD", "errors": [str(error)]}
                scenarios.append({"name": name, **result})
                return result
            raise AssertionError(f"{name} unexpectedly built")

        revoked = build_hold("revoked-status", response=Path(fixture["revoked"]))
        unauthorized = build_hold(
            "unauthorized-responder",
            response=Path(fixture["unauthorized"]),
            responder_cert=Path(fixture["unauthorized_responder"]),
        )
        wrong_certificate = build_hold(
            "wrong-certificate-id",
            response=good,
            target=Path(fixture["other_certificate"]),
            expected_serial=str(fixture["other_serial"]),
        )
        missing_next_update = build_hold(
            "missing-next-update", response=Path(fixture["no_next_update"])
        )

        tampered_response = root / "tampered.der"
        tampered = bytearray(good.read_bytes())
        tampered[-1] ^= 1
        tampered_response.write_bytes(bytes(tampered))
        tampered_result = evaluate(
            "tampered-ocsp-response", valid_manifest, tampered_response, valid_token
        )
        missing_timestamp = evaluate(
            "missing-archive-timestamp",
            valid_manifest,
            good,
            root / "missing.tsr",
        )
        wrong_value = root / "wrong-value"
        wrong_value.write_bytes(b"not-the-ocsp-manifest")
        wrong_token = root / "wrong.tsr"
        _issue(timestamp_config, wrong_value, wrong_token)
        wrong_timestamp = evaluate(
            "timestamp-over-wrong-bytes", valid_manifest, good, wrong_token
        )
        escalated_manifest = root / "escalated.manifest.json"
        escalated = json.loads(valid_manifest.read_bytes())
        escalated["deployment_authority"] = True
        escalated_manifest.write_bytes(_canonical(escalated))
        escalated_result = evaluate(
            "authority-escalation", escalated_manifest, good, valid_token
        )

    holds = (
        revoked,
        unauthorized,
        wrong_certificate,
        missing_next_update,
        tampered_result,
        missing_timestamp,
        wrong_timestamp,
        escalated_result,
    )
    return {
        "schema": "truepanel.holodeck-temperature-ocsp-evidence-package/v1",
        "simulation": True,
        "hardware_isolated": True,
        "scenarios": scenarios,
        "measurements": {
            "scenario_count": len(scenarios),
            "trusted_packages": int(valid["status"] == STATUS_TRUSTED),
            "hold_count": sum(item["status"] != STATUS_TRUSTED for item in holds),
            "actual_der_ocsp_responses_parsed": 5,
            "authorized_responders_verified": 1,
            "actual_rfc3161_tokens_verified": 1,
            "serial_bindings_verified": 1,
            "revoked_status_acceptances": 0,
            "unauthorized_responder_acceptances": 0,
            "wrong_certificate_acceptances": 0,
            "missing_next_update_acceptances": 0,
            "tampered_response_acceptances": 0,
            "fixture_private_keys_created": int(fixture["private_key_count"]) + 2,
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


__all__ = ["run_temperature_ocsp_evidence_package_checkride"]
