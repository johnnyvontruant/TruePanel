"""Content-addressed CRL evidence package with archive timestamp renewal."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

from .rfc3161_timestamp import OpenSslRfc3161TimestampVerifier
from .ssh_verifier import OpenSshSignatureVerifier
from .temperature_calibration_candidate_appraisal import _canonical, _snapshot

SCHEMA: Final = "truepanel.aegis-temperature-revocation-evidence-package/v1"
MANIFEST_SCHEMA: Final = f"{SCHEMA}-manifest"
STATUS_TRUSTED: Final = "REVOCATION_EVIDENCE_PACKAGE_TRUSTED"
STATUS_REQUIRED: Final = "ACTION_REQUIRED_REVOCATION_EVIDENCE_PACKAGE"
STATUS_HOLD: Final = "HOLD"
MAX_DER_BYTES: Final = 256 * 1024
MAX_CERTIFICATE_BYTES: Final = 128 * 1024

_SERIAL = re.compile(r"^serial=([0-9A-F]+)$", re.MULTILINE)
_ISSUER = re.compile(r"^issuer=(.+)$", re.MULTILINE)
_FINGERPRINT = re.compile(
    r"^(?:sha256|sha2-256) Fingerprint=(.+)$", re.MULTILINE | re.IGNORECASE
)
_LAST_UPDATE = re.compile(r"^lastUpdate=(.+)$", re.MULTILINE)
_NEXT_UPDATE = re.compile(r"^nextUpdate=(.+)$", re.MULTILINE)
_REVOKED_SERIAL = re.compile(r"Serial Number:\s*([0-9A-F]+)", re.IGNORECASE)
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


def _openssl_time(value: str) -> str:
    parsed = datetime.strptime(value.strip(), "%b %d %H:%M:%S %Y GMT").replace(
        tzinfo=UTC
    )
    return parsed.isoformat().replace("+00:00", "Z")


def _time(value: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError("RevocationEvidenceTimeInvalid")
    parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    if parsed.tzinfo != UTC:
        raise ValueError("RevocationEvidenceTimeInvalid")
    return parsed


def _normal_serial(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9A-Fa-f]+", value):
        raise ValueError("RevocationEvidenceSerialInvalid")
    return value.upper().lstrip("0") or "0"


class OpenSslDerCrlInspector:
    """Verify and inspect exact DER CRL bytes with a protected issuer."""

    def __init__(self, *, executable: str = "/usr/bin/openssl", timeout: float = 5.0):
        self.executable = executable
        self.timeout = float(timeout)

    def __call__(
        self,
        tsa_certificate: bytes,
        issuer_certificate: bytes,
        crl_der: bytes,
        expected_serial_hex: str,
    ) -> dict[str, Any]:
        result: dict[str, Any] = {
            "verified": False,
            "certificate_serial_hex": None,
            "certificate_status": None,
            "issuer": None,
            "crl_sha256_fingerprint": None,
            "this_update_utc": None,
            "next_update_utc": None,
            "crl_sha256": None,
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
                or not isinstance(crl_der, bytes)
                or not crl_der
                or len(crl_der) > MAX_DER_BYTES
                or not Path(self.executable).is_absolute()
            ):
                raise ValueError("RevocationEvidenceInputInvalid")
            expected = _normal_serial(expected_serial_hex)
            cert_fd = OpenSshSignatureVerifier._memfd(
                "truepanel-tsa-cert", tsa_certificate
            )
            issuer_fd = OpenSshSignatureVerifier._memfd(
                "truepanel-tsa-issuer", issuer_certificate
            )
            crl_fd = OpenSshSignatureVerifier._memfd("truepanel-tsa-crl", crl_der)
            descriptors.extend((cert_fd, issuer_fd, crl_fd))
            cert_path = f"/proc/self/fd/{cert_fd}"
            issuer_path = f"/proc/self/fd/{issuer_fd}"
            crl_path = f"/proc/self/fd/{crl_fd}"
            pass_fds = tuple(descriptors)
            verified_cert = subprocess.run(
                [self.executable, "verify", "-CAfile", issuer_path, cert_path],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=self.timeout,
                check=False,
                pass_fds=pass_fds,
            )
            verified_crl = subprocess.run(
                [
                    self.executable,
                    "crl",
                    "-inform",
                    "DER",
                    "-in",
                    crl_path,
                    "-CAfile",
                    issuer_path,
                    "-verify",
                    "-noout",
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=self.timeout,
                check=False,
                pass_fds=pass_fds,
            )
            if verified_cert.returncode or verified_crl.returncode:
                raise ValueError("RevocationEvidenceSignatureInvalid")
            cert = subprocess.run(
                [
                    self.executable,
                    "x509",
                    "-in",
                    cert_path,
                    "-noout",
                    "-serial",
                    "-issuer",
                ],
                capture_output=True,
                text=True,
                timeout=self.timeout,
                check=False,
                pass_fds=pass_fds,
            )
            crl = subprocess.run(
                [
                    self.executable,
                    "crl",
                    "-inform",
                    "DER",
                    "-in",
                    crl_path,
                    "-noout",
                    "-issuer",
                    "-lastupdate",
                    "-nextupdate",
                    "-fingerprint",
                    "-sha256",
                    "-text",
                ],
                capture_output=True,
                text=True,
                timeout=self.timeout,
                check=False,
                pass_fds=pass_fds,
            )
            if cert.returncode or crl.returncode or len(crl.stdout) > 128 * 1024:
                raise ValueError("RevocationEvidenceInspectionFailed")
            serial = _SERIAL.search(cert.stdout)
            cert_issuer = _ISSUER.search(cert.stdout)
            crl_issuer = _ISSUER.search(crl.stdout)
            fingerprint = _FINGERPRINT.search(crl.stdout)
            last_update = _LAST_UPDATE.search(crl.stdout)
            next_update = _NEXT_UPDATE.search(crl.stdout)
            if not all(
                (serial, cert_issuer, crl_issuer, fingerprint, last_update, next_update)
            ):
                raise ValueError("RevocationEvidenceProfileInvalid")
            actual = _normal_serial(serial.group(1))
            if actual != expected:
                raise ValueError("RevocationEvidenceSerialMismatch")
            if cert_issuer.group(1).strip() != crl_issuer.group(1).strip():
                raise ValueError("RevocationEvidenceIssuerMismatch")
            revoked = {
                _normal_serial(value) for value in _REVOKED_SERIAL.findall(crl.stdout)
            }
            status = "REVOKED" if actual in revoked else "NOT_LISTED"
            if status != "NOT_LISTED":
                raise ValueError("RevocationEvidenceCertificateRevoked")
            result.update(
                {
                    "verified": True,
                    "certificate_serial_hex": actual,
                    "certificate_status": status,
                    "issuer": crl_issuer.group(1).strip(),
                    "crl_sha256_fingerprint": fingerprint.group(1)
                    .replace(":", "")
                    .lower(),
                    "this_update_utc": _openssl_time(last_update.group(1)),
                    "next_update_utc": _openssl_time(next_update.group(1)),
                    "crl_sha256": hashlib.sha256(crl_der).hexdigest(),
                }
            )
        except (OSError, subprocess.SubprocessError, UnicodeError, ValueError) as error:
            result["errors"].append(str(error) or error.__class__.__name__)
        finally:
            for descriptor in descriptors:
                os.close(descriptor)
        return result


def build_revocation_evidence_manifest(
    inspector: OpenSslDerCrlInspector,
    operator: str,
    tsa_certificate: bytes,
    issuer_certificate: bytes,
    crl_der: bytes,
    expected_serial_hex: str,
) -> bytes:
    if not isinstance(operator, str) or not operator.strip():
        raise ValueError("RevocationEvidenceOperatorInvalid")
    inspection = inspector(
        tsa_certificate, issuer_certificate, crl_der, expected_serial_hex
    )
    if not inspection["verified"]:
        raise ValueError(inspection["errors"][0])
    manifest = {
        "schema": MANIFEST_SCHEMA,
        "scope": "timestamp-authority-revocation-evidence-only",
        "operator": operator,
        "evidence_type": "CRL",
        "evidence_encoding": "DER",
        "tsa_certificate_sha256": hashlib.sha256(tsa_certificate).hexdigest(),
        "issuer_certificate_sha256": hashlib.sha256(issuer_certificate).hexdigest(),
        "crl_sha256": inspection["crl_sha256"],
        "certificate_serial_hex": inspection["certificate_serial_hex"],
        "certificate_status": inspection["certificate_status"],
        "issuer": inspection["issuer"],
        "crl_sha256_fingerprint": inspection["crl_sha256_fingerprint"],
        "this_update_utc": inspection["this_update_utc"],
        "next_update_utc": inspection["next_update_utc"],
        "archive_timestamp_required": True,
        **{key: False for key in _DENIED},
    }
    manifest["manifest_sha256"] = hashlib.sha256(_canonical(manifest)).hexdigest()
    return _canonical(manifest)


def evaluate_revocation_evidence_package(
    inspector: OpenSslDerCrlInspector,
    timestamp_verifier: OpenSslRfc3161TimestampVerifier,
    operator: str,
    expected_serial_hex: str,
    manifest_path: str | Path,
    tsa_certificate_path: str | Path,
    issuer_certificate_path: str | Path,
    crl_path: str | Path,
    archive_timestamp_path: str | Path,
) -> dict[str, Any]:
    errors: list[str] = []
    inspection_verified = timestamp_verified = False
    serial = evidence_sha = renewed_at = valid_until = None
    try:
        manifest_bytes = _snapshot(Path(manifest_path), MAX_DER_BYTES)
        manifest = json.loads(manifest_bytes)
        tsa_certificate = _snapshot(Path(tsa_certificate_path), MAX_CERTIFICATE_BYTES)
        issuer_certificate = _snapshot(
            Path(issuer_certificate_path), MAX_CERTIFICATE_BYTES
        )
        crl_der = _snapshot(Path(crl_path), MAX_DER_BYTES)
        archive_path = Path(archive_timestamp_path)
        if not archive_path.exists():
            raise ValueError("RevocationEvidenceArchiveTimestampRequired")
        token = _snapshot(archive_path, MAX_DER_BYTES)
        expected = build_revocation_evidence_manifest(
            inspector,
            operator,
            tsa_certificate,
            issuer_certificate,
            crl_der,
            expected_serial_hex,
        )
        inspection_verified = True
        if manifest_bytes != expected:
            raise ValueError("RevocationEvidenceManifestMismatch")
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
            raise ValueError("RevocationEvidenceArchiveTimestampOutsideValidity")
        timestamp_verified = True
        serial = manifest["certificate_serial_hex"]
        evidence_sha = manifest["crl_sha256"]
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
        "der_crl_verified": inspection_verified,
        "certificate_serial_hex": serial,
        "certificate_status": "NOT_LISTED" if trusted else None,
        "evidence_sha256": evidence_sha,
        "archive_timestamp_verified": timestamp_verified,
        "renewed_at_utc": renewed_at,
        "evidence_valid_until_utc": valid_until,
        "eligible_for_timestamp_trust_rotation": trusted,
        **{key: False for key in _DENIED},
        "errors": errors,
    }


def pending_revocation_evidence_package(rotation: dict[str, Any]) -> dict[str, Any]:
    ready = rotation.get("rotation_authorized") is True
    return {
        "schema": SCHEMA,
        "status": STATUS_REQUIRED if ready else STATUS_HOLD,
        "der_crl_verified": False,
        "certificate_serial_hex": None,
        "certificate_status": None,
        "evidence_sha256": None,
        "archive_timestamp_verified": False,
        "renewed_at_utc": None,
        "evidence_valid_until_utc": None,
        "eligible_for_timestamp_trust_rotation": False,
        **{key: False for key in _DENIED},
        "next_action": "Archive the exact DER CRL, bind the TSA certificate serial, and timestamp the manifest before the CRL expires.",
    }


__all__ = [
    "OpenSslDerCrlInspector",
    "STATUS_TRUSTED",
    "build_revocation_evidence_manifest",
    "evaluate_revocation_evidence_package",
    "pending_revocation_evidence_package",
]
