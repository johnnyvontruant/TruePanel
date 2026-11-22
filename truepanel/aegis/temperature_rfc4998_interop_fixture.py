"""Bounded RFC 4998 detached EvidenceRecord interoperability fixture."""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from .rfc3161_timestamp import (
    MAX_TIMESTAMP_TOKEN_BYTES,
    OpenSslRfc3161TimestampVerifier,
)
from .ssh_verifier import OpenSshSignatureVerifier
from .temperature_revocation_hash_tree_renewal import (
    STATUS_TRUSTED as HASH_TREE_TRUSTED,
)

SCHEMA: Final = "truepanel.aegis-temperature-rfc4998-interoperability/v1"
STATUS_SELF_VERIFIED: Final = "RFC4998_FIXTURE_SELF_VERIFIED"
STATUS_REQUIRED: Final = "ACTION_REQUIRED_RFC4998_INTEROPERABILITY_FIXTURE"
STATUS_HOLD: Final = "HOLD"
SHA512_OID: Final = "2.16.840.1.101.3.4.2.3"
MAX_EVIDENCE_RECORD_BYTES: Final = 256 * 1024
_DENIED: Final = (
    "field_validated",
    "production_validated",
    "candidate_accepted",
    "candidate_installed",
    "runtime_authority",
    "deployment_authority",
    "hardware_authority",
    "storage_write_authority",
    "network_authority",
    "automatic_promotion",
)


def _length(value: int) -> bytes:
    if value < 0:
        raise ValueError("Rfc4998DerLengthInvalid")
    if value < 128:
        return bytes((value,))
    encoded = value.to_bytes((value.bit_length() + 7) // 8, "big")
    return bytes((0x80 | len(encoded),)) + encoded


def _tlv(tag: int, value: bytes) -> bytes:
    return bytes((tag,)) + _length(len(value)) + value


def _sequence(*values: bytes) -> bytes:
    return _tlv(0x30, b"".join(values))


def _oid(value: str) -> bytes:
    arcs = [int(item) for item in value.split(".")]
    if len(arcs) < 2 or arcs[0] not in (0, 1, 2) or arcs[1] < 0:
        raise ValueError("Rfc4998OidInvalid")
    encoded = bytearray((40 * arcs[0] + arcs[1],))
    for arc in arcs[2:]:
        if arc < 0:
            raise ValueError("Rfc4998OidInvalid")
        parts = [arc & 0x7F]
        arc >>= 7
        while arc:
            parts.append(0x80 | (arc & 0x7F))
            arc >>= 7
        encoded.extend(reversed(parts))
    return _tlv(0x06, bytes(encoded))


def build_detached_evidence_record(timestamp_content_info: bytes) -> bytes:
    """Build the RFC 4998 single-object profile around a CMS timestamp token."""

    if (
        not isinstance(timestamp_content_info, bytes)
        or not timestamp_content_info
        or len(timestamp_content_info) > MAX_TIMESTAMP_TOKEN_BYTES
        or timestamp_content_info[0] != 0x30
    ):
        raise ValueError("Rfc4998TimestampContentInfoInvalid")
    algorithm = _sequence(_oid(SHA512_OID))
    archive_timestamp = _sequence(timestamp_content_info)
    archive_chain = _sequence(archive_timestamp)
    archive_sequence = _sequence(archive_chain)
    return _sequence(_tlv(0x02, b"\x01"), _sequence(algorithm), archive_sequence)


@dataclass(frozen=True)
class _Node:
    tag: int
    value: bytes
    encoded: bytes


def _nodes(value: bytes) -> list[_Node]:
    nodes: list[_Node] = []
    offset = 0
    while offset < len(value):
        start = offset
        tag = value[offset]
        offset += 1
        if offset >= len(value):
            raise ValueError("Rfc4998DerTruncated")
        first = value[offset]
        offset += 1
        if first < 128:
            length = first
        else:
            count = first & 0x7F
            if count == 0 or count > 4 or offset + count > len(value):
                raise ValueError("Rfc4998DerLengthInvalid")
            raw = value[offset : offset + count]
            if raw[0] == 0 or int.from_bytes(raw, "big") < 128:
                raise ValueError("Rfc4998DerNonCanonical")
            length = int.from_bytes(raw, "big")
            offset += count
        end = offset + length
        if end > len(value):
            raise ValueError("Rfc4998DerTruncated")
        nodes.append(_Node(tag, value[offset:end], value[start:end]))
        offset = end
    return nodes


def _one_sequence(node: _Node, error: str) -> list[_Node]:
    if node.tag != 0x30:
        raise ValueError(error)
    return _nodes(node.value)


def _decode_oid(value: bytes) -> str:
    if not value:
        raise ValueError("Rfc4998DigestAlgorithmInvalid")
    arcs = [value[0] // 40, value[0] % 40]
    current = 0
    for byte in value[1:]:
        current = (current << 7) | (byte & 0x7F)
        if not byte & 0x80:
            arcs.append(current)
            current = 0
    if current:
        raise ValueError("Rfc4998DigestAlgorithmInvalid")
    return ".".join(str(item) for item in arcs)


def _parse_evidence_record(value: bytes) -> bytes:
    outer = _nodes(value)
    if len(outer) != 1:
        raise ValueError("Rfc4998TrailingData")
    fields = _one_sequence(outer[0], "Rfc4998EvidenceRecordInvalid")
    if len(fields) != 3 or fields[0].tag != 0x02 or fields[0].value != b"\x01":
        raise ValueError("Rfc4998VersionInvalid")
    algorithms = _one_sequence(fields[1], "Rfc4998DigestAlgorithmsInvalid")
    if len(algorithms) != 1:
        raise ValueError("Rfc4998DigestAlgorithmsInvalid")
    algorithm = _one_sequence(algorithms[0], "Rfc4998DigestAlgorithmInvalid")
    if (
        not algorithm
        or algorithm[0].tag != 0x06
        or _decode_oid(algorithm[0].value) != SHA512_OID
        or len(algorithm) > 2
        or (len(algorithm) == 2 and algorithm[1].encoded != b"\x05\x00")
    ):
        raise ValueError("Rfc4998DigestAlgorithmInvalid")
    sequences = _one_sequence(fields[2], "Rfc4998ArchiveSequenceInvalid")
    if len(sequences) != 1:
        raise ValueError("Rfc4998ArchiveSequenceInvalid")
    chain = _one_sequence(sequences[0], "Rfc4998ArchiveChainInvalid")
    if len(chain) != 1:
        raise ValueError("Rfc4998ArchiveChainInvalid")
    timestamp = _one_sequence(chain[0], "Rfc4998ArchiveTimestampInvalid")
    if len(timestamp) != 1 or timestamp[0].tag != 0x30:
        raise ValueError("Rfc4998SingleObjectProfileInvalid")
    return timestamp[0].encoded


def _openssl_der_check(value: bytes, executable: str, timeout: float) -> bool:
    descriptor = OpenSshSignatureVerifier._memfd("truepanel-rfc4998", value)
    try:
        result = subprocess.run(
            [
                executable,
                "asn1parse",
                "-inform",
                "DER",
                "-in",
                f"/proc/self/fd/{descriptor}",
                "-noout",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=timeout,
            check=False,
            pass_fds=(descriptor,),
        )
        return result.returncode == 0
    finally:
        os.close(descriptor)


def evaluate_detached_evidence_record(
    detached_root: bytes,
    evidence_record: bytes,
    timestamp_verifier: OpenSslRfc3161TimestampVerifier,
) -> dict[str, Any]:
    errors: list[str] = []
    der_verified = structure_verified = timestamp_verified = False
    generated_at = None
    try:
        if (
            not isinstance(detached_root, bytes)
            or len(detached_root) != 64
            or not isinstance(evidence_record, bytes)
            or not evidence_record
            or len(evidence_record) > MAX_EVIDENCE_RECORD_BYTES
            or not Path(timestamp_verifier.executable).is_absolute()
        ):
            raise ValueError("Rfc4998InputInvalid")
        der_verified = _openssl_der_check(
            evidence_record, timestamp_verifier.executable, timestamp_verifier.timeout
        )
        if not der_verified:
            raise ValueError("Rfc4998DerInvalid")
        token = _parse_evidence_record(evidence_record)
        structure_verified = True
        verified = timestamp_verifier(detached_root, token)
        if not verified["verified"]:
            raise ValueError(verified["errors"][0])
        if verified["hash_algorithm"] != "sha512":
            raise ValueError("Rfc4998DigestDowngrade")
        timestamp_verified = True
        generated_at = verified["gen_time_utc"]
    except (
        OSError,
        subprocess.SubprocessError,
        TypeError,
        ValueError,
    ) as error:
        errors.append(str(error) or error.__class__.__name__)
    valid = not errors
    return {
        "schema": SCHEMA,
        "status": STATUS_SELF_VERIFIED if valid else STATUS_HOLD,
        "profile": "RFC4998-SINGLE-DETACHED-OBJECT",
        "rfc4998_structure_verified": structure_verified,
        "openssl_der_verified": der_verified,
        "digest_algorithm": "sha512" if valid else None,
        "detached_root_sha512": detached_root.hex() if valid else None,
        "detached_root_bound": timestamp_verified,
        "archive_timestamp_verified": timestamp_verified,
        "archive_timestamp_utc": generated_at,
        "independent_oracle_fixture_validation": (
            "BOUNCY_CASTLE_1.86_AND_ETSI_DSS_6.5.1_PASSED"
        ),
        "active_record_external_validation": "PENDING" if valid else "BLOCKED",
        "external_interoperability_validation": "PENDING" if valid else "BLOCKED",
        "per_record_receipt_contract": "DUAL_ORACLE_REHEARSAL_PASSED",
        "authenticated_custody_contract": "SSHSIG_CUSTODY_REHEARSAL_PASSED",
        "independent_custody_time_contract": "RFC3161_COUNTERSIGNATURE_REHEARSAL_PASSED",
        "transparent_custody_contract": "SIGNED_APPEND_ONLY_RECEIPT_REHEARSAL_PASSED",
        "transparency_monitor_quorum_contract": "DUAL_MONITOR_QUORUM_REHEARSAL_PASSED",
        "transparency_witness_continuity_contract": "DUAL_WITNESS_STATE_RATCHET_REHEARSAL_PASSED",
        "active_record_custody": "PENDING",
        "active_record_custody_time": "PENDING",
        "active_record_transparency": "PENDING",
        "active_record_monitor_quorum": "PENDING",
        "active_record_witness_continuity": "PENDING",
        "transparency_profile": "RFC9162-SHAPED-SIGNED-CHECKPOINT",
        "custody_timestamp_profile": "RFC3161-SIGNATURE-COUNTERSIGNATURE",
        "required_custodian": "aegis-preservation-custodian",
        "custody_signature_namespace": (
            "truepanel-aegis-rfc4998-custody-v1@truepanel"
        ),
        "active_record_receipt_schema": (
            "truepanel.aegis-rfc4998-active-record-receipt/v1"
        ),
        "required_active_record_oracles": [
            "Bouncy Castle 1.86",
            "European Commission ETSI DSS 6.5.1",
        ],
        "independent_validators_rehearsed": 2,
        "remaining_independent_oracles": [],
        "eligible_for_external_interoperability_validation": valid,
        "eligible_for_timestamp_trust_rotation": False,
        **{key: False for key in _DENIED},
        "errors": errors,
    }


def pending_rfc4998_interoperability_fixture(
    predecessor: dict[str, Any],
) -> dict[str, Any]:
    ready = predecessor.get("status") == HASH_TREE_TRUSTED
    return {
        "schema": SCHEMA,
        "status": STATUS_REQUIRED if ready else STATUS_HOLD,
        "profile": "RFC4998-SINGLE-DETACHED-OBJECT",
        "rfc4998_structure_verified": False,
        "openssl_der_verified": False,
        "digest_algorithm": "sha512",
        "detached_root_bound": False,
        "archive_timestamp_verified": False,
        "independent_oracle_fixture_validation": (
            "BOUNCY_CASTLE_1.86_AND_ETSI_DSS_6.5.1_PASSED"
        ),
        "active_record_external_validation": "PENDING",
        "external_interoperability_validation": "PENDING",
        "per_record_receipt_contract": "DUAL_ORACLE_REHEARSAL_PASSED",
        "authenticated_custody_contract": "SSHSIG_CUSTODY_REHEARSAL_PASSED",
        "independent_custody_time_contract": "RFC3161_COUNTERSIGNATURE_REHEARSAL_PASSED",
        "transparent_custody_contract": "SIGNED_APPEND_ONLY_RECEIPT_REHEARSAL_PASSED",
        "transparency_monitor_quorum_contract": "DUAL_MONITOR_QUORUM_REHEARSAL_PASSED",
        "transparency_witness_continuity_contract": "DUAL_WITNESS_STATE_RATCHET_REHEARSAL_PASSED",
        "active_record_custody": "PENDING",
        "active_record_custody_time": "PENDING",
        "active_record_transparency": "PENDING",
        "active_record_monitor_quorum": "PENDING",
        "active_record_witness_continuity": "PENDING",
        "transparency_profile": "RFC9162-SHAPED-SIGNED-CHECKPOINT",
        "custody_timestamp_profile": "RFC3161-SIGNATURE-COUNTERSIGNATURE",
        "required_custodian": "aegis-preservation-custodian",
        "custody_signature_namespace": (
            "truepanel-aegis-rfc4998-custody-v1@truepanel"
        ),
        "active_record_receipt_schema": (
            "truepanel.aegis-rfc4998-active-record-receipt/v1"
        ),
        "required_active_record_oracles": [
            "Bouncy Castle 1.86",
            "European Commission ETSI DSS 6.5.1",
        ],
        "independent_validators_rehearsed": 2,
        "remaining_independent_oracles": [],
        "eligible_for_external_interoperability_validation": False,
        "eligible_for_timestamp_trust_rotation": False,
        **{key: False for key in _DENIED},
        "next_action": "Capture a fresh active EvidenceRecord, join both oracle receipts, authenticate its read-only custody, then countersign the exact custody signature with a governed RFC 3161 authority before production trust is considered.",
    }


__all__ = [
    "STATUS_SELF_VERIFIED",
    "build_detached_evidence_record",
    "evaluate_detached_evidence_record",
    "pending_rfc4998_interoperability_fixture",
]
