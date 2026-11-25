"""Combined CRL/OCSP archive renewal with exact predecessor evidence binding."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from .rfc3161_timestamp import OpenSslRfc3161TimestampVerifier
from .temperature_calibration_candidate_appraisal import _canonical, _snapshot
from .temperature_ocsp_evidence_package import (
    OpenSslDerOcspInspector,
    evaluate_ocsp_evidence_package,
)
from .temperature_revocation_evidence_package import (
    MAX_DER_BYTES,
    OpenSslDerCrlInspector,
    _time,
    evaluate_revocation_evidence_package,
)

SCHEMA: Final = "truepanel.aegis-temperature-revocation-archive-renewal/v1"
MANIFEST_SCHEMA: Final = f"{SCHEMA}-manifest"
STATUS_TRUSTED: Final = "REVOCATION_ARCHIVE_RENEWAL_TRUSTED"
STATUS_REQUIRED: Final = "ACTION_REQUIRED_REVOCATION_ARCHIVE_RENEWAL"
STATUS_HOLD: Final = "HOLD"
MAX_RENEWAL_MANIFEST_BYTES: Final = 512 * 1024

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


@dataclass(frozen=True)
class CrlEvidenceInputs:
    operator: str
    expected_serial_hex: str
    manifest_path: str | Path
    tsa_certificate_path: str | Path
    issuer_certificate_path: str | Path
    crl_path: str | Path
    archive_timestamp_path: str | Path


@dataclass(frozen=True)
class OcspEvidenceInputs:
    operator: str
    expected_serial_hex: str
    manifest_path: str | Path
    tsa_certificate_path: str | Path
    issuer_certificate_path: str | Path
    responder_certificate_path: str | Path
    ocsp_path: str | Path
    archive_timestamp_path: str | Path


def _verified_manifest(value: bytes, expected_schema: str) -> dict[str, Any]:
    manifest = json.loads(value)
    if not isinstance(manifest, dict) or manifest.get("schema") != expected_schema:
        raise ValueError("ArchiveRenewalPredecessorManifestInvalid")
    claimed = manifest.get("manifest_sha256")
    unsigned = dict(manifest)
    unsigned.pop("manifest_sha256", None)
    if claimed != hashlib.sha256(_canonical(unsigned)).hexdigest():
        raise ValueError("ArchiveRenewalPredecessorManifestDigestInvalid")
    return manifest


def _prior_entry(
    evidence_type: str,
    package: dict[str, Any],
    manifest_bytes: bytes,
    timestamp_bytes: bytes,
) -> dict[str, Any]:
    expected_schema = (
        "truepanel.aegis-temperature-revocation-evidence-package/v1-manifest"
        if evidence_type == "CRL"
        else "truepanel.aegis-temperature-ocsp-evidence-package/v1-manifest"
    )
    manifest = _verified_manifest(manifest_bytes, expected_schema)
    required_status = (
        "REVOCATION_EVIDENCE_PACKAGE_TRUSTED"
        if evidence_type == "CRL"
        else "OCSP_EVIDENCE_PACKAGE_TRUSTED"
    )
    evidence_key = "crl_sha256" if evidence_type == "CRL" else "ocsp_sha256"
    if (
        package.get("status") != required_status
        or package.get("archive_timestamp_verified") is not True
        or package.get("eligible_for_timestamp_trust_rotation") is not True
        or package.get("certificate_serial_hex")
        != manifest.get("certificate_serial_hex")
        or package.get("evidence_sha256") != manifest.get(evidence_key)
        or package.get("evidence_valid_until_utc") != manifest.get("next_update_utc")
        or not package.get("renewed_at_utc")
        or not timestamp_bytes
    ):
        raise ValueError(f"ArchiveRenewal{evidence_type}PackageUntrusted")
    return {
        "evidence_type": evidence_type,
        "operator": manifest["operator"],
        "certificate_serial_hex": manifest["certificate_serial_hex"],
        "tsa_certificate_sha256": manifest["tsa_certificate_sha256"],
        "issuer_certificate_sha256": manifest["issuer_certificate_sha256"],
        "evidence_sha256": manifest[evidence_key],
        "evidence_manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "archive_timestamp_sha256": hashlib.sha256(timestamp_bytes).hexdigest(),
        "initial_archived_at_utc": package["renewed_at_utc"],
        "evidence_valid_until_utc": package["evidence_valid_until_utc"],
    }


def build_revocation_archive_renewal_manifest(
    crl_package: dict[str, Any],
    ocsp_package: dict[str, Any],
    crl_manifest_bytes: bytes,
    crl_timestamp_bytes: bytes,
    ocsp_manifest_bytes: bytes,
    ocsp_timestamp_bytes: bytes,
    *,
    previous_generation: int,
    renewal_generation: int,
    timestamp_authority_valid_until_utc: str,
    digest_policy_valid_until_utc: str,
) -> bytes:
    if (
        not isinstance(previous_generation, int)
        or previous_generation < 1
        or renewal_generation != previous_generation + 1
    ):
        raise ValueError("ArchiveRenewalGenerationInvalid")
    crl = _prior_entry("CRL", crl_package, crl_manifest_bytes, crl_timestamp_bytes)
    ocsp = _prior_entry("OCSP", ocsp_package, ocsp_manifest_bytes, ocsp_timestamp_bytes)
    identity_fields = (
        "operator",
        "certificate_serial_hex",
        "tsa_certificate_sha256",
        "issuer_certificate_sha256",
    )
    if any(crl[field] != ocsp[field] for field in identity_fields):
        raise ValueError("ArchiveRenewalEvidenceIdentityMismatch")
    authority_deadline = _time(timestamp_authority_valid_until_utc)
    digest_deadline = _time(digest_policy_valid_until_utc)
    initial_archived = max(
        _time(crl["initial_archived_at_utc"]),
        _time(ocsp["initial_archived_at_utc"]),
    )
    deadline = min(
        _time(crl["evidence_valid_until_utc"]),
        _time(ocsp["evidence_valid_until_utc"]),
        authority_deadline,
        digest_deadline,
    )
    if deadline < initial_archived:
        raise ValueError("ArchiveRenewalDeadlineAlreadyExpired")
    entries = [crl, ocsp]
    entries.sort(key=lambda item: item["evidence_type"])
    manifest = {
        "schema": MANIFEST_SCHEMA,
        "scope": "timestamp-authority-revocation-archive-renewal-only",
        "profile": "ERS-INSPIRED-TIMESTAMP-RENEWAL",
        "rfc4998_wire_compatible": False,
        "previous_generation": previous_generation,
        "renewal_generation": renewal_generation,
        "renewal_mode": "TIMESTAMP_RENEWAL",
        "digest_algorithm": "sha256",
        "operator": crl["operator"],
        "certificate_serial_hex": crl["certificate_serial_hex"],
        "tsa_certificate_sha256": crl["tsa_certificate_sha256"],
        "issuer_certificate_sha256": crl["issuer_certificate_sha256"],
        "prior_archive_entries": entries,
        "prior_archive_set_sha256": hashlib.sha256(_canonical(entries)).hexdigest(),
        "previous_archived_at_utc": initial_archived.isoformat().replace("+00:00", "Z"),
        "timestamp_authority_valid_until_utc": timestamp_authority_valid_until_utc,
        "digest_policy_valid_until_utc": digest_policy_valid_until_utc,
        "renewal_deadline_utc": deadline.isoformat().replace("+00:00", "Z"),
        "archive_timestamp_required": True,
        **{key: False for key in _DENIED},
    }
    manifest["manifest_sha256"] = hashlib.sha256(_canonical(manifest)).hexdigest()
    return _canonical(manifest)


def evaluate_revocation_archive_renewal(
    crl_inspector: OpenSslDerCrlInspector,
    ocsp_inspector: OpenSslDerOcspInspector,
    timestamp_verifier: OpenSslRfc3161TimestampVerifier,
    crl_inputs: CrlEvidenceInputs,
    ocsp_inputs: OcspEvidenceInputs,
    renewal_manifest_path: str | Path,
    renewal_timestamp_path: str | Path,
    *,
    previous_generation: int,
    renewal_generation: int,
    timestamp_authority_valid_until_utc: str,
    digest_policy_valid_until_utc: str,
) -> dict[str, Any]:
    errors: list[str] = []
    predecessors_verified = timestamp_verified = False
    renewed_at = deadline = set_sha = None
    try:
        crl_package = evaluate_revocation_evidence_package(
            crl_inspector,
            timestamp_verifier,
            crl_inputs.operator,
            crl_inputs.expected_serial_hex,
            crl_inputs.manifest_path,
            crl_inputs.tsa_certificate_path,
            crl_inputs.issuer_certificate_path,
            crl_inputs.crl_path,
            crl_inputs.archive_timestamp_path,
        )
        ocsp_package = evaluate_ocsp_evidence_package(
            ocsp_inspector,
            timestamp_verifier,
            ocsp_inputs.operator,
            ocsp_inputs.expected_serial_hex,
            ocsp_inputs.manifest_path,
            ocsp_inputs.tsa_certificate_path,
            ocsp_inputs.issuer_certificate_path,
            ocsp_inputs.responder_certificate_path,
            ocsp_inputs.ocsp_path,
            ocsp_inputs.archive_timestamp_path,
        )
        if crl_package["status"] != "REVOCATION_EVIDENCE_PACKAGE_TRUSTED":
            raise ValueError("ArchiveRenewalCRLPackageUntrusted")
        if ocsp_package["status"] != "OCSP_EVIDENCE_PACKAGE_TRUSTED":
            raise ValueError("ArchiveRenewalOCSPPackageUntrusted")
        crl_manifest = _snapshot(
            Path(crl_inputs.manifest_path), MAX_RENEWAL_MANIFEST_BYTES
        )
        crl_timestamp = _snapshot(
            Path(crl_inputs.archive_timestamp_path), MAX_DER_BYTES
        )
        ocsp_manifest = _snapshot(
            Path(ocsp_inputs.manifest_path), MAX_RENEWAL_MANIFEST_BYTES
        )
        ocsp_timestamp = _snapshot(
            Path(ocsp_inputs.archive_timestamp_path), MAX_DER_BYTES
        )
        expected = build_revocation_archive_renewal_manifest(
            crl_package,
            ocsp_package,
            crl_manifest,
            crl_timestamp,
            ocsp_manifest,
            ocsp_timestamp,
            previous_generation=previous_generation,
            renewal_generation=renewal_generation,
            timestamp_authority_valid_until_utc=timestamp_authority_valid_until_utc,
            digest_policy_valid_until_utc=digest_policy_valid_until_utc,
        )
        predecessors_verified = True
        manifest_bytes = _snapshot(
            Path(renewal_manifest_path), MAX_RENEWAL_MANIFEST_BYTES
        )
        if manifest_bytes != expected:
            raise ValueError("ArchiveRenewalManifestMismatch")
        renewal_timestamp = Path(renewal_timestamp_path)
        if not renewal_timestamp.exists():
            raise ValueError("ArchiveRenewalTimestampRequired")
        timestamp_bytes = _snapshot(renewal_timestamp, MAX_DER_BYTES)
        verified = timestamp_verifier(manifest_bytes, timestamp_bytes)
        if not verified["verified"]:
            raise ValueError(verified["errors"][0])
        manifest = json.loads(manifest_bytes)
        renewed_at = verified["gen_time_utc"]
        deadline = manifest["renewal_deadline_utc"]
        if not (
            _time(manifest["previous_archived_at_utc"])
            <= _time(renewed_at)
            <= _time(deadline)
        ):
            raise ValueError("ArchiveRenewalTimestampOutsideValidity")
        timestamp_verified = True
        set_sha = manifest["prior_archive_set_sha256"]
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
        "predecessor_packages_verified": predecessors_verified,
        "crl_and_ocsp_bound": trusted,
        "previous_generation": previous_generation if trusted else None,
        "renewal_generation": renewal_generation if trusted else None,
        "prior_archive_set_sha256": set_sha,
        "archive_timestamp_verified": timestamp_verified,
        "renewed_at_utc": renewed_at,
        "renewal_deadline_utc": deadline,
        "eligible_for_timestamp_trust_rotation": trusted,
        **{key: False for key in _DENIED},
        "errors": errors,
    }


def pending_revocation_archive_renewal(
    ocsp_package: dict[str, Any],
) -> dict[str, Any]:
    ready = ocsp_package.get("eligible_for_timestamp_trust_rotation") is True
    return {
        "schema": SCHEMA,
        "status": STATUS_REQUIRED if ready else STATUS_HOLD,
        "predecessor_packages_verified": False,
        "crl_and_ocsp_bound": False,
        "previous_generation": None,
        "renewal_generation": None,
        "prior_archive_set_sha256": None,
        "archive_timestamp_verified": False,
        "renewed_at_utc": None,
        "renewal_deadline_utc": None,
        "eligible_for_timestamp_trust_rotation": False,
        **{key: False for key in _DENIED},
        "next_action": "Re-verify the exact CRL and OCSP packages, bind both prior timestamp tokens, and renew the combined archive before its earliest governed deadline.",
    }


__all__ = [
    "CrlEvidenceInputs",
    "OcspEvidenceInputs",
    "STATUS_TRUSTED",
    "build_revocation_archive_renewal_manifest",
    "evaluate_revocation_archive_renewal",
    "pending_revocation_archive_renewal",
]
