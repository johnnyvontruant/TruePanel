"""Signed OCSP evidence package with delegated-responder verification."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any, Final

from .rfc3161_timestamp import OpenSslRfc3161TimestampVerifier
from .ssh_verifier import OpenSshSignatureVerifier
from .temperature_calibration_candidate_appraisal import _canonical, _snapshot
from .temperature_revocation_evidence_package import (
    MAX_CERTIFICATE_BYTES,
    MAX_DER_BYTES,
    _normal_serial,
    _openssl_time,
    _time,
)

SCHEMA: Final = "truepanel.aegis-temperature-ocsp-evidence-package/v1"
MANIFEST_SCHEMA: Final = f"{SCHEMA}-manifest"
STATUS_TRUSTED: Final = "OCSP_EVIDENCE_PACKAGE_TRUSTED"
STATUS_REQUIRED: Final = "ACTION_REQUIRED_OCSP_EVIDENCE_PACKAGE"
STATUS_HOLD: Final = "HOLD"

_CERT_SERIAL = re.compile(r"^serial=([0-9A-F]+)$", re.MULTILINE)
_RESPONSE_STATUS = re.compile(r"^\s*OCSP Response Status:\s+successful", re.MULTILINE)
_SERIAL = re.compile(r"^\s*Serial Number:\s*([0-9A-F]+)\s*$", re.MULTILINE)
_STATUS = re.compile(r"^\s*Cert Status:\s*(\S+)\s*$", re.MULTILINE)
_RESPONDER = re.compile(r"^\s*Responder Id:\s*(.+)$", re.MULTILINE)
_PRODUCED = re.compile(r"^\s*Produced At:\s*(.+)$", re.MULTILINE)
_THIS_UPDATE = re.compile(r"^\s*This Update:\s*(.+)$", re.MULTILINE)
_NEXT_UPDATE = re.compile(r"^\s*Next Update:\s*(.+)$", re.MULTILINE)
_DENIED = (
    "field_validated",
    "production_validated",
    "candidate_accepted",
    "candidate_installed",
    "capture_authority",
    "runtime_authority",
    "deployment_authority",
    "hardware_authority",
    "storage_write_authority",
    "network_authority",
    "automatic_promotion",
)


class OpenSslDerOcspInspector:
    """Verify exact DER OCSP bytes and one explicitly supplied responder."""

    def __init__(self, *, executable: str = "/usr/bin/openssl", timeout: float = 5.0):
        self.executable = executable
        self.timeout = float(timeout)

    def __call__(
        self,
        tsa_certificate: bytes,
        issuer_certificate: bytes,
        responder_certificate: bytes,
        ocsp_der: bytes,
        expected_serial_hex: str,
    ) -> dict[str, Any]:
        result: dict[str, Any] = {
            "verified": False,
            "certificate_serial_hex": None,
            "certificate_status": None,
            "responder_id": None,
            "produced_at_utc": None,
            "this_update_utc": None,
            "next_update_utc": None,
            "ocsp_sha256": None,
            "errors": [],
        }
        descriptors: list[int] = []
        try:
            if (
                not isinstance(tsa_certificate, bytes)
                or not tsa_certificate
                or len(tsa_certificate) > MAX_CERTIFICATE_BYTES
                or not isinstance(issuer_certificate, bytes)
                or not issuer_certificate
                or len(issuer_certificate) > MAX_CERTIFICATE_BYTES
                or not isinstance(responder_certificate, bytes)
                or not responder_certificate
                or len(responder_certificate) > MAX_CERTIFICATE_BYTES
                or not isinstance(ocsp_der, bytes)
                or not ocsp_der
                or len(ocsp_der) > MAX_DER_BYTES
                or not Path(self.executable).is_absolute()
            ):
                raise ValueError("OcspEvidenceInputInvalid")
            expected = _normal_serial(expected_serial_hex)
            cert_fd = OpenSshSignatureVerifier._memfd(
                "truepanel-ocsp-tsa", tsa_certificate
            )
            issuer_fd = OpenSshSignatureVerifier._memfd(
                "truepanel-ocsp-issuer", issuer_certificate
            )
            responder_fd = OpenSshSignatureVerifier._memfd(
                "truepanel-ocsp-responder", responder_certificate
            )
            response_fd = OpenSshSignatureVerifier._memfd(
                "truepanel-ocsp-response", ocsp_der
            )
            descriptors.extend((cert_fd, issuer_fd, responder_fd, response_fd))
            cert_path = f"/proc/self/fd/{cert_fd}"
            issuer_path = f"/proc/self/fd/{issuer_fd}"
            responder_path = f"/proc/self/fd/{responder_fd}"
            response_path = f"/proc/self/fd/{response_fd}"
            pass_fds = tuple(descriptors)
            certificate = subprocess.run(
                [self.executable, "x509", "-in", cert_path, "-noout", "-serial"],
                capture_output=True,
                text=True,
                timeout=self.timeout,
                check=False,
                pass_fds=pass_fds,
            )
            serial = _CERT_SERIAL.search(certificate.stdout)
            if certificate.returncode or not serial:
                raise ValueError("OcspEvidenceCertificateInvalid")
            actual = _normal_serial(serial.group(1))
            if actual != expected:
                raise ValueError("OcspEvidenceSerialMismatch")
            inspected = subprocess.run(
                [
                    self.executable,
                    "ocsp",
                    "-respin",
                    response_path,
                    "-issuer",
                    issuer_path,
                    "-cert",
                    cert_path,
                    "-CAfile",
                    issuer_path,
                    "-verify_other",
                    responder_path,
                    "-no_intern",
                    "-no_nonce",
                    "-validity_period",
                    "300",
                    "-resp_text",
                ],
                capture_output=True,
                text=True,
                timeout=self.timeout,
                check=False,
                pass_fds=pass_fds,
            )
            if (
                inspected.returncode
                or len(inspected.stdout) > 128 * 1024
                or "Response verify OK" not in inspected.stderr
            ):
                raise ValueError("OcspEvidenceVerificationFailed")
            response_status = _RESPONSE_STATUS.search(inspected.stdout)
            response_serials = {
                _normal_serial(value) for value in _SERIAL.findall(inspected.stdout)
            }
            statuses = {value.lower() for value in _STATUS.findall(inspected.stdout)}
            responder = _RESPONDER.search(inspected.stdout)
            produced = _PRODUCED.search(inspected.stdout)
            this_update = _THIS_UPDATE.search(inspected.stdout)
            next_update = _NEXT_UPDATE.search(inspected.stdout)
            if not all(
                (response_status, responder, produced, this_update, next_update)
            ) or response_serials != {actual}:
                raise ValueError("OcspEvidenceProfileInvalid")
            if statuses != {"good"}:
                raise ValueError("OcspEvidenceCertificateNotGood")
            result.update(
                {
                    "verified": True,
                    "certificate_serial_hex": actual,
                    "certificate_status": "GOOD",
                    "responder_id": responder.group(1).strip(),
                    "produced_at_utc": _openssl_time(produced.group(1)),
                    "this_update_utc": _openssl_time(this_update.group(1)),
                    "next_update_utc": _openssl_time(next_update.group(1)),
                    "ocsp_sha256": hashlib.sha256(ocsp_der).hexdigest(),
                }
            )
        except (OSError, subprocess.SubprocessError, UnicodeError, ValueError) as error:
            result["errors"].append(str(error) or error.__class__.__name__)
        finally:
            for descriptor in descriptors:
                os.close(descriptor)
        return result


def build_ocsp_evidence_manifest(
    inspector: OpenSslDerOcspInspector,
    operator: str,
    tsa_certificate: bytes,
    issuer_certificate: bytes,
    responder_certificate: bytes,
    ocsp_der: bytes,
    expected_serial_hex: str,
) -> bytes:
    if not isinstance(operator, str) or not operator.strip():
        raise ValueError("OcspEvidenceOperatorInvalid")
    inspection = inspector(
        tsa_certificate,
        issuer_certificate,
        responder_certificate,
        ocsp_der,
        expected_serial_hex,
    )
    if not inspection["verified"]:
        raise ValueError(inspection["errors"][0])
    manifest = {
        "schema": MANIFEST_SCHEMA,
        "scope": "timestamp-authority-ocsp-evidence-only",
        "operator": operator,
        "evidence_type": "OCSP",
        "evidence_encoding": "DER",
        "tsa_certificate_sha256": hashlib.sha256(tsa_certificate).hexdigest(),
        "issuer_certificate_sha256": hashlib.sha256(issuer_certificate).hexdigest(),
        "responder_certificate_sha256": hashlib.sha256(
            responder_certificate
        ).hexdigest(),
        "ocsp_sha256": inspection["ocsp_sha256"],
        "certificate_serial_hex": inspection["certificate_serial_hex"],
        "certificate_status": inspection["certificate_status"],
        "responder_id": inspection["responder_id"],
        "produced_at_utc": inspection["produced_at_utc"],
        "this_update_utc": inspection["this_update_utc"],
        "next_update_utc": inspection["next_update_utc"],
        "direct_issuer_delegation_required": True,
        "ocsp_signing_eku_required": True,
        "archive_timestamp_required": True,
        **{key: False for key in _DENIED},
    }
    manifest["manifest_sha256"] = hashlib.sha256(_canonical(manifest)).hexdigest()
    return _canonical(manifest)


def evaluate_ocsp_evidence_package(
    inspector: OpenSslDerOcspInspector,
    timestamp_verifier: OpenSslRfc3161TimestampVerifier,
    operator: str,
    expected_serial_hex: str,
    manifest_path: str | Path,
    tsa_certificate_path: str | Path,
    issuer_certificate_path: str | Path,
    responder_certificate_path: str | Path,
    ocsp_path: str | Path,
    archive_timestamp_path: str | Path,
) -> dict[str, Any]:
    errors: list[str] = []
    ocsp_verified = timestamp_verified = False
    serial = responder = evidence_sha = renewed_at = valid_until = None
    try:
        manifest_bytes = _snapshot(Path(manifest_path), MAX_DER_BYTES)
        manifest = json.loads(manifest_bytes)
        tsa_certificate = _snapshot(Path(tsa_certificate_path), MAX_CERTIFICATE_BYTES)
        issuer_certificate = _snapshot(
            Path(issuer_certificate_path), MAX_CERTIFICATE_BYTES
        )
        responder_certificate = _snapshot(
            Path(responder_certificate_path), MAX_CERTIFICATE_BYTES
        )
        ocsp_der = _snapshot(Path(ocsp_path), MAX_DER_BYTES)
        archive_path = Path(archive_timestamp_path)
        if not archive_path.exists():
            raise ValueError("OcspEvidenceArchiveTimestampRequired")
        token = _snapshot(archive_path, MAX_DER_BYTES)
        expected = build_ocsp_evidence_manifest(
            inspector,
            operator,
            tsa_certificate,
            issuer_certificate,
            responder_certificate,
            ocsp_der,
            expected_serial_hex,
        )
        ocsp_verified = True
        if manifest_bytes != expected:
            raise ValueError("OcspEvidenceManifestMismatch")
        timestamp = timestamp_verifier(manifest_bytes, token)
        if not timestamp["verified"]:
            raise ValueError(timestamp["errors"][0])
        renewed_at = timestamp["gen_time_utc"]
        valid_until = manifest["next_update_utc"]
        if not (
            _time(manifest["this_update_utc"])
            <= _time(renewed_at)
            <= _time(valid_until)
        ):
            raise ValueError("OcspEvidenceArchiveTimestampOutsideValidity")
        timestamp_verified = True
        serial = manifest["certificate_serial_hex"]
        responder = manifest["responder_id"]
        evidence_sha = manifest["ocsp_sha256"]
    except (
        FileNotFoundError,
        json.JSONDecodeError,
        KeyError,
        OSError,
        TypeError,
        UnicodeDecodeError,
        ValueError,
    ) as error:
        errors.append(str(error) or error.__class__.__name__)
    trusted = not errors
    return {
        "schema": SCHEMA,
        "status": STATUS_TRUSTED if trusted else STATUS_HOLD,
        "der_ocsp_verified": ocsp_verified,
        "certificate_serial_hex": serial,
        "certificate_status": "GOOD" if trusted else None,
        "responder_authorized": trusted,
        "responder_id": responder,
        "evidence_sha256": evidence_sha,
        "archive_timestamp_verified": timestamp_verified,
        "renewed_at_utc": renewed_at,
        "evidence_valid_until_utc": valid_until,
        "eligible_for_timestamp_trust_rotation": trusted,
        **{key: False for key in _DENIED},
        "errors": errors,
    }


def pending_ocsp_evidence_package(crl_package: dict[str, Any]) -> dict[str, Any]:
    ready = crl_package.get("eligible_for_timestamp_trust_rotation") is True
    return {
        "schema": SCHEMA,
        "status": STATUS_REQUIRED if ready else STATUS_HOLD,
        "der_ocsp_verified": False,
        "certificate_serial_hex": None,
        "certificate_status": None,
        "responder_authorized": False,
        "responder_id": None,
        "evidence_sha256": None,
        "archive_timestamp_verified": False,
        "renewed_at_utc": None,
        "evidence_valid_until_utc": None,
        "eligible_for_timestamp_trust_rotation": False,
        **{key: False for key in _DENIED},
        "next_action": "Archive a signed DER OCSP response from the issuer or a directly delegated OCSPSigning responder, then timestamp its manifest before nextUpdate.",
    }


__all__ = [
    "OpenSslDerOcspInspector",
    "STATUS_TRUSTED",
    "build_ocsp_evidence_manifest",
    "evaluate_ocsp_evidence_package",
    "pending_ocsp_evidence_package",
]
