"""Digest-agile renewal of the complete revocation evidence archive."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from .rfc3161_timestamp import OpenSslRfc3161TimestampVerifier
from .temperature_calibration_candidate_appraisal import _canonical, _snapshot
from .temperature_ocsp_evidence_package import OpenSslDerOcspInspector
from .temperature_revocation_archive_renewal import (
    STATUS_TRUSTED as PREDECESSOR_TRUSTED,
)
from .temperature_revocation_archive_renewal import (
    CrlEvidenceInputs,
    OcspEvidenceInputs,
    evaluate_revocation_archive_renewal,
)
from .temperature_revocation_evidence_package import (
    MAX_DER_BYTES,
    OpenSslDerCrlInspector,
    _time,
)

SCHEMA: Final = "truepanel.aegis-temperature-revocation-hash-tree-renewal/v1"
MANIFEST_SCHEMA: Final = f"{SCHEMA}-manifest"
STATUS_TRUSTED: Final = "REVOCATION_HASH_TREE_RENEWAL_TRUSTED"
STATUS_REQUIRED: Final = "ACTION_REQUIRED_REVOCATION_HASH_TREE_RENEWAL"
STATUS_HOLD: Final = "HOLD"
MAX_ARCHIVE_OBJECT_BYTES: Final = 2 * 1024 * 1024
MAX_MANIFEST_BYTES: Final = 512 * 1024

REQUIRED_OBJECT_LABELS: Final = frozenset(
    {
        "crl.der",
        "ocsp.der",
        "tsa-certificate.pem",
        "issuer-certificate.pem",
        "ocsp-responder-certificate.pem",
        "crl-manifest.json",
        "crl-timestamp.tsr",
        "ocsp-manifest.json",
        "ocsp-timestamp.tsr",
        "combined-renewal-manifest.json",
        "combined-renewal-timestamp.tsr",
    }
)
_SEQUENCE_LABELS: Final = (
    "crl-manifest.json",
    "crl-timestamp.tsr",
    "ocsp-manifest.json",
    "ocsp-timestamp.tsr",
    "combined-renewal-manifest.json",
    "combined-renewal-timestamp.tsr",
)
_DENIED: Final = (
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
class ArchiveObject:
    label: str
    path: str | Path


def _hash(value: bytes) -> bytes:
    return hashlib.sha512(value).digest()


def _split(count: int) -> int:
    return 1 << ((count - 1).bit_length() - 1)


def _merkle_root(values: Sequence[bytes]) -> bytes:
    """RFC 9162 tree shape and domain separation, using SHA-512."""

    if not values:
        return _hash(b"")
    if len(values) == 1:
        return _hash(b"\x00" + values[0])
    split = _split(len(values))
    return _hash(b"\x01" + _merkle_root(values[:split]) + _merkle_root(values[split:]))


def _inclusion_proof(values: Sequence[bytes], index: int) -> list[dict[str, str]]:
    if len(values) <= 1:
        return []
    split = _split(len(values))
    if index < split:
        return _inclusion_proof(values[:split], index) + [
            {"side": "right", "sha512": _merkle_root(values[split:]).hex()}
        ]
    return _inclusion_proof(values[split:], index - split) + [
        {"side": "left", "sha512": _merkle_root(values[:split]).hex()}
    ]


def verify_inclusion(
    leaf: bytes, proof: Sequence[dict[str, str]], expected_root_hex: str
) -> bool:
    current = _hash(b"\x00" + leaf)
    try:
        for item in proof:
            sibling = bytes.fromhex(item["sha512"])
            current = (
                _hash(b"\x01" + sibling + current)
                if item["side"] == "left"
                else _hash(b"\x01" + current + sibling)
            )
        return current.hex() == expected_root_hex
    except (KeyError, TypeError, ValueError):
        return False


def _framed_sequence(objects: dict[str, bytes]) -> bytes:
    framed = bytearray(b"TRUEPANEL-ARCHIVE-SEQUENCE-V1\x00")
    for label in _SEQUENCE_LABELS:
        value = objects[label]
        encoded = label.encode("ascii")
        framed.extend(len(encoded).to_bytes(2, "big"))
        framed.extend(encoded)
        framed.extend(len(value).to_bytes(8, "big"))
        framed.extend(value)
    return bytes(framed)


def _archive_objects(items: Sequence[ArchiveObject]) -> dict[str, bytes]:
    if len(items) != len(REQUIRED_OBJECT_LABELS):
        raise ValueError("HashTreeRenewalArchiveObjectSetIncomplete")
    values: dict[str, bytes] = {}
    for item in items:
        if item.label in values or item.label not in REQUIRED_OBJECT_LABELS:
            raise ValueError("HashTreeRenewalArchiveObjectSetInvalid")
        values[item.label] = _snapshot(
            Path(item.path),
            MAX_DER_BYTES
            if item.label.endswith((".der", ".tsr"))
            else MAX_ARCHIVE_OBJECT_BYTES,
        )
    if set(values) != REQUIRED_OBJECT_LABELS:
        raise ValueError("HashTreeRenewalArchiveObjectSetIncomplete")
    return values


def build_revocation_hash_tree_renewal_manifest(
    predecessor: dict[str, Any],
    archive_objects: Sequence[ArchiveObject],
    *,
    previous_generation: int,
    renewal_generation: int,
    previous_chain: int,
    renewal_chain: int,
    new_timestamp_authority_valid_until_utc: str,
    new_digest_policy_valid_until_utc: str,
) -> bytes:
    if predecessor.get("status") != PREDECESSOR_TRUSTED:
        raise ValueError("HashTreeRenewalPredecessorUntrusted")
    if (
        previous_generation != predecessor.get("renewal_generation")
        or renewal_generation != previous_generation + 1
        or previous_chain < 1
        or renewal_chain != previous_chain + 1
    ):
        raise ValueError("HashTreeRenewalGenerationInvalid")
    objects = _archive_objects(archive_objects)
    predecessor_manifest = json.loads(objects["combined-renewal-manifest.json"])
    if (
        predecessor_manifest.get("schema")
        != "truepanel.aegis-temperature-revocation-archive-renewal/v1-manifest"
        or predecessor_manifest.get("renewal_generation") != previous_generation
        or predecessor_manifest.get("digest_algorithm") != "sha256"
    ):
        raise ValueError("HashTreeRenewalPredecessorManifestInvalid")
    old_deadline = _time(predecessor_manifest["digest_policy_valid_until_utc"])
    new_deadline = _time(new_digest_policy_valid_until_utc)
    authority_deadline = _time(new_timestamp_authority_valid_until_utc)
    if new_deadline <= old_deadline or authority_deadline <= _time(
        predecessor["renewed_at_utc"]
    ):
        raise ValueError("HashTreeRenewalPolicyWindowInvalid")

    sequence_bytes = _framed_sequence(objects)
    sequence_digest = _hash(sequence_bytes)
    entries: list[dict[str, Any]] = []
    leaves: list[bytes] = []
    for label in sorted(objects):
        value = objects[label]
        data_digest = _hash(value)
        linked_digest = _hash(data_digest + sequence_digest)
        entry = {
            "label": label,
            "size_bytes": len(value),
            "sha256": hashlib.sha256(value).hexdigest(),
            "sha512": data_digest.hex(),
            "archive_sequence_sha512": sequence_digest.hex(),
            "renewal_leaf_sha512": linked_digest.hex(),
        }
        entries.append(entry)
        leaves.append(
            _canonical({"label": label, "renewal_leaf_sha512": linked_digest.hex()})
        )
    root = _merkle_root(leaves).hex()
    proofs = [
        {
            "label": entry["label"],
            "leaf": json.loads(leaves[index]),
            "path": _inclusion_proof(leaves, index),
        }
        for index, entry in enumerate(entries)
    ]
    if not all(
        verify_inclusion(leaves[index], proof["path"], root)
        for index, proof in enumerate(proofs)
    ):
        raise ValueError("HashTreeRenewalInclusionProofInvalid")
    manifest = {
        "schema": MANIFEST_SCHEMA,
        "scope": "timestamp-authority-revocation-hash-tree-renewal-only",
        "profile": "ERS-INSPIRED-HASH-TREE-RENEWAL",
        "rfc4998_wire_compatible": False,
        "tree_profile": "RFC9162-DOMAIN-SEPARATED-BINARY-SHA512",
        "previous_generation": previous_generation,
        "renewal_generation": renewal_generation,
        "previous_chain": previous_chain,
        "renewal_chain": renewal_chain,
        "renewal_mode": "HASH_TREE_RENEWAL",
        "digest_algorithms": ["sha256", "sha512"],
        "retired_digest_algorithm": "sha256",
        "active_digest_algorithm": "sha512",
        "archive_object_count": len(entries),
        "archive_objects": entries,
        "archive_sequence_sha512": sequence_digest.hex(),
        "merkle_root_sha512": root,
        "inclusion_proofs": proofs,
        "previous_archived_at_utc": predecessor["renewed_at_utc"],
        "old_digest_policy_valid_until_utc": predecessor_manifest[
            "digest_policy_valid_until_utc"
        ],
        "new_digest_policy_valid_until_utc": new_digest_policy_valid_until_utc,
        "new_timestamp_authority_valid_until_utc": new_timestamp_authority_valid_until_utc,
        "renewal_deadline_utc": min(old_deadline, authority_deadline)
        .isoformat()
        .replace("+00:00", "Z"),
        "archive_timestamp_required": True,
        **{key: False for key in _DENIED},
    }
    manifest["manifest_sha256"] = hashlib.sha256(_canonical(manifest)).hexdigest()
    return _canonical(manifest)


def evaluate_revocation_hash_tree_renewal(
    crl_inspector: OpenSslDerCrlInspector,
    ocsp_inspector: OpenSslDerOcspInspector,
    predecessor_timestamp_verifier: OpenSslRfc3161TimestampVerifier,
    renewal_timestamp_verifier: OpenSslRfc3161TimestampVerifier,
    crl_inputs: CrlEvidenceInputs,
    ocsp_inputs: OcspEvidenceInputs,
    archive_objects: Sequence[ArchiveObject],
    predecessor_manifest_path: str | Path,
    predecessor_timestamp_path: str | Path,
    renewal_manifest_path: str | Path,
    renewal_timestamp_path: str | Path,
    *,
    previous_generation: int,
    renewal_generation: int,
    previous_chain: int,
    renewal_chain: int,
    new_timestamp_authority_valid_until_utc: str,
    new_digest_policy_valid_until_utc: str,
) -> dict[str, Any]:
    errors: list[str] = []
    predecessor_verified = objects_rehashed = proofs_verified = timestamp_verified = (
        False
    )
    root = renewed_at = deadline = None
    try:
        predecessor_manifest = json.loads(
            _snapshot(Path(predecessor_manifest_path), MAX_MANIFEST_BYTES)
        )
        predecessor = evaluate_revocation_archive_renewal(
            crl_inspector,
            ocsp_inspector,
            predecessor_timestamp_verifier,
            crl_inputs,
            ocsp_inputs,
            predecessor_manifest_path,
            predecessor_timestamp_path,
            previous_generation=previous_generation - 1,
            renewal_generation=previous_generation,
            timestamp_authority_valid_until_utc=predecessor_manifest[
                "timestamp_authority_valid_until_utc"
            ],
            digest_policy_valid_until_utc=predecessor_manifest[
                "digest_policy_valid_until_utc"
            ],
        )
        if predecessor["status"] != PREDECESSOR_TRUSTED:
            raise ValueError("HashTreeRenewalPredecessorUntrusted")
        predecessor_verified = True
        expected = build_revocation_hash_tree_renewal_manifest(
            predecessor,
            archive_objects,
            previous_generation=previous_generation,
            renewal_generation=renewal_generation,
            previous_chain=previous_chain,
            renewal_chain=renewal_chain,
            new_timestamp_authority_valid_until_utc=new_timestamp_authority_valid_until_utc,
            new_digest_policy_valid_until_utc=new_digest_policy_valid_until_utc,
        )
        supplied = _snapshot(Path(renewal_manifest_path), MAX_MANIFEST_BYTES)
        if supplied != expected:
            raise ValueError("HashTreeRenewalManifestMismatch")
        manifest = json.loads(supplied)
        objects_rehashed = manifest["archive_object_count"] == len(
            REQUIRED_OBJECT_LABELS
        )
        proofs_verified = all(
            verify_inclusion(
                _canonical(proof["leaf"]),
                proof["path"],
                manifest["merkle_root_sha512"],
            )
            for proof in manifest["inclusion_proofs"]
        )
        if not objects_rehashed or not proofs_verified:
            raise ValueError("HashTreeRenewalCoverageInvalid")
        token = _snapshot(Path(renewal_timestamp_path), MAX_DER_BYTES)
        root_bytes = bytes.fromhex(manifest["merkle_root_sha512"])
        verified = renewal_timestamp_verifier(root_bytes, token)
        if not verified["verified"]:
            raise ValueError(verified["errors"][0])
        if verified["hash_algorithm"] != "sha512":
            raise ValueError("HashTreeRenewalDigestDowngrade")
        renewed_at = verified["gen_time_utc"]
        deadline = manifest["renewal_deadline_utc"]
        if not (
            _time(manifest["previous_archived_at_utc"])
            <= _time(renewed_at)
            <= _time(deadline)
            < _time(manifest["new_digest_policy_valid_until_utc"])
        ):
            raise ValueError("HashTreeRenewalTimestampOutsideValidity")
        timestamp_verified = True
        root = manifest["merkle_root_sha512"]
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
        "predecessor_archive_verified": predecessor_verified,
        "complete_archive_rehashed": objects_rehashed,
        "archive_object_count": len(REQUIRED_OBJECT_LABELS) if objects_rehashed else 0,
        "inclusion_proofs_verified": proofs_verified,
        "previous_generation": previous_generation if trusted else None,
        "renewal_generation": renewal_generation if trusted else None,
        "previous_chain": previous_chain if trusted else None,
        "renewal_chain": renewal_chain if trusted else None,
        "retired_digest_algorithm": "sha256" if trusted else None,
        "active_digest_algorithm": "sha512" if trusted else None,
        "merkle_root_sha512": root,
        "archive_timestamp_verified": timestamp_verified,
        "renewed_at_utc": renewed_at,
        "renewal_deadline_utc": deadline,
        "eligible_for_timestamp_trust_rotation": trusted,
        **{key: False for key in _DENIED},
        "errors": errors,
    }


def pending_revocation_hash_tree_renewal(
    predecessor: dict[str, Any],
) -> dict[str, Any]:
    ready = predecessor.get("status") == PREDECESSOR_TRUSTED
    return {
        "schema": SCHEMA,
        "status": STATUS_REQUIRED if ready else STATUS_HOLD,
        "predecessor_archive_verified": False,
        "complete_archive_rehashed": False,
        "archive_object_count": 0,
        "inclusion_proofs_verified": False,
        "previous_generation": None,
        "renewal_generation": None,
        "previous_chain": None,
        "renewal_chain": None,
        "retired_digest_algorithm": "sha256",
        "active_digest_algorithm": "sha512",
        "merkle_root_sha512": None,
        "archive_timestamp_verified": False,
        "eligible_for_timestamp_trust_rotation": False,
        **{key: False for key in _DENIED},
        "next_action": "Rehash every archived object and the complete prior sequence with SHA-512, verify every inclusion proof, and timestamp the new root before SHA-256 policy expiry.",
    }


__all__ = [
    "ArchiveObject",
    "REQUIRED_OBJECT_LABELS",
    "STATUS_TRUSTED",
    "build_revocation_hash_tree_renewal_manifest",
    "evaluate_revocation_hash_tree_renewal",
    "pending_revocation_hash_tree_renewal",
    "verify_inclusion",
]
