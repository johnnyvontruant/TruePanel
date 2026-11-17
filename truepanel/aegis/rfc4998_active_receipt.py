"""Fail-closed join for per-record RFC 4998 oracle receipts."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any, Final

SCHEMA: Final = "truepanel.aegis-rfc4998-active-record-receipt/v1"
MANIFEST_SCHEMA: Final = "truepanel.aegis-rfc4998-active-record-manifest/v1"
STATUS_REHEARSED: Final = "DUAL_ORACLE_REHEARSED"

_ORACLES: Final = {
    "Bouncy Castle": {
        "version": "1.86",
        "schema": "truepanel.aegis-rfc4998-bouncycastle-receipt/v1",
        "claims": (
            "record_parsed",
            "der_round_trip_exact",
            "detached_data_present",
            "timestamp_signature_valid",
            "pkix_chain_valid_at_timestamp",
            "wrong_data_rejected",
            "truncated_record_rejected",
            "wrong_trust_anchor_rejected",
        ),
    },
    "European Commission ETSI DSS": {
        "version": "6.5.1",
        "schema": "truepanel.aegis-rfc4998-etsi-dss-receipt/v1",
        "claims": (
            "record_parsed",
            "structural_validation_valid",
            "detached_data_found",
            "detached_data_intact",
            "timestamp_signature_valid",
            "timestamp_imprint_intact",
            "trust_anchor_reached",
            "wrong_data_rejected",
            "truncated_record_rejected",
            "wrong_trust_anchor_rejected",
        ),
    },
}


class ActiveReceiptError(ValueError):
    """Raised when receipts cannot be safely joined."""


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _hex(value: Any, length: int, name: str) -> str:
    if not isinstance(value, str) or len(value) != length:
        raise ActiveReceiptError(f"{name}Invalid")
    try:
        bytes.fromhex(value)
    except ValueError as error:
        raise ActiveReceiptError(f"{name}Invalid") from error
    return value.lower()


def join_active_record_receipts(
    manifest: dict[str, Any], receipts: Iterable[dict[str, Any]]
) -> dict[str, Any]:
    """Bind exact oracle verdicts to one immutable record and detached object."""

    if manifest.get("schema") != MANIFEST_SCHEMA:
        raise ActiveReceiptError("ManifestSchemaUnsupported")
    record_id = manifest.get("record_id")
    if not isinstance(record_id, str) or not record_id:
        raise ActiveReceiptError("RecordIdInvalid")
    if manifest.get("profile") != "RFC4998-SINGLE-DETACHED-OBJECT":
        raise ActiveReceiptError("ProfileUnsupported")
    subjects = manifest.get("subjects")
    if not isinstance(subjects, list) or len(subjects) != 2:
        raise ActiveReceiptError("SubjectSetInvalid")
    by_name = {item.get("name"): item for item in subjects if isinstance(item, dict)}
    if set(by_name) != {"evidence-record", "detached-data"}:
        raise ActiveReceiptError("SubjectSetInvalid")
    record_sha256 = _hex(
        by_name["evidence-record"].get("digest", {}).get("sha256"),
        64,
        "RecordDigest",
    )
    detached_sha512 = _hex(
        by_name["detached-data"].get("digest", {}).get("sha512"),
        128,
        "DetachedDigest",
    )
    required = manifest.get("required_oracles")
    expected = {name: policy["version"] for name, policy in _ORACLES.items()}
    if required != expected:
        raise ActiveReceiptError("OraclePolicyMismatch")

    indexed: dict[str, dict[str, Any]] = {}
    receipt_evidence: list[dict[str, str]] = []
    for receipt in receipts:
        if not isinstance(receipt, dict):
            raise ActiveReceiptError("ReceiptInvalid")
        name = receipt.get("oracle")
        if name in indexed:
            raise ActiveReceiptError("DuplicateOracleReceipt")
        policy = _ORACLES.get(name)
        if policy is None:
            raise ActiveReceiptError("UnexpectedOracleReceipt")
        if receipt.get("oracle_version") != policy["version"]:
            raise ActiveReceiptError("OracleVersionMismatch")
        if receipt.get("schema") != policy["schema"]:
            raise ActiveReceiptError("OracleSchemaMismatch")
        if receipt.get("fixture_sha256") != record_sha256:
            raise ActiveReceiptError("RecordDigestMismatch")
        if receipt.get("detached_data_sha512") != detached_sha512:
            raise ActiveReceiptError("DetachedDigestMismatch")
        if any(receipt.get(claim) is not True for claim in policy["claims"]):
            raise ActiveReceiptError("OracleVerdictIncomplete")
        if any(
            receipt.get(denial) is not False
            for denial in (
                "production_trusted",
                "deployment_authority",
                "hardware_authority",
            )
        ):
            raise ActiveReceiptError("AuthorityEscalation")
        indexed[name] = receipt
        receipt_evidence.append(
            {
                "oracle": name,
                "oracle_version": policy["version"],
                "canonical_receipt_sha256": hashlib.sha256(
                    _canonical(receipt)
                ).hexdigest(),
            }
        )
    if set(indexed) != set(_ORACLES):
        raise ActiveReceiptError("RequiredOracleMissing")

    return {
        "schema": SCHEMA,
        "record_id": record_id,
        "profile": manifest["profile"],
        "subjects": subjects,
        "oracle_receipts": sorted(receipt_evidence, key=lambda item: item["oracle"]),
        "all_required_oracles_present": True,
        "subject_digests_agree": True,
        "positive_verdicts_complete": True,
        "active_record_external_validation": STATUS_REHEARSED,
        "eligible_for_production_trust": False,
        "production_trusted": False,
        "deployment_authority": False,
        "hardware_authority": False,
        "network_authority": False,
        "storage_authority": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("receipts", nargs="+", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    manifest = json.loads(args.manifest.read_text())
    receipts = [json.loads(path.read_text()) for path in args.receipts]
    result = join_active_record_receipts(manifest, receipts)
    rendered = _canonical(result).decode() + "\n"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered)
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "ActiveReceiptError",
    "MANIFEST_SCHEMA",
    "SCHEMA",
    "STATUS_REHEARSED",
    "join_active_record_receipts",
]
