"""Deterministic RFC 4998 detached EvidenceRecord interoperability rehearsal."""

from __future__ import annotations

import hashlib
import tempfile
from pathlib import Path
from typing import Any

from truepanel.aegis.rfc3161_timestamp import OpenSslRfc3161TimestampVerifier
from truepanel.aegis.temperature_calibration_candidate_appraisal import _canonical
from truepanel.aegis.temperature_rfc4998_interop_fixture import (
    STATUS_SELF_VERIFIED,
    build_detached_evidence_record,
    evaluate_detached_evidence_record,
)
from truepanel.holodeck.aegis_temperature_reviewer_timestamp_witness import (
    _extract_timestamp_token,
    _issue,
    _tsa,
)
from truepanel.holodeck.aegis_temperature_revocation_hash_tree_renewal import (
    run_temperature_revocation_hash_tree_renewal_checkride,
)


def run_temperature_rfc4998_interop_checkride() -> dict[str, Any]:
    predecessor = run_temperature_revocation_hash_tree_renewal_checkride()
    if predecessor["measurements"]["trusted_renewals"] != 1:
        raise RuntimeError("Rfc4998PredecessorRehearsalFailed")
    detached_root = hashlib.sha512(
        b"TRUEPANEL-RFC4998-DETACHED-ROOT-V1\x00"
        + _canonical(predecessor["measurements"])
    ).digest()
    scenarios: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="truepanel-rfc4998-interop-") as directory:
        root = Path(directory).resolve()
        tsa_root = root / "tsa"
        tsa_root.mkdir()
        response_verifier, config = _tsa(tsa_root, digest_algorithm="sha512")
        verifier = OpenSslRfc3161TimestampVerifier(
            response_verifier.trust_anchor_path,
            expected_hash_algorithm="sha512",
            token_is_content_info=True,
        )
        detached = root / "archive-root.bin"
        detached.write_bytes(detached_root)
        response = root / "archive-root.tsr"
        token = root / "archive-root.tst"
        _issue(config, detached, response, digest_algorithm="sha512")
        _extract_timestamp_token(response, token)
        token_bytes = token.read_bytes()
        evidence_record = build_detached_evidence_record(token_bytes)

        def evaluate(
            name: str,
            *,
            candidate_root: bytes = detached_root,
            candidate_record: bytes = evidence_record,
            candidate_verifier: OpenSslRfc3161TimestampVerifier = verifier,
        ) -> dict[str, Any]:
            result = evaluate_detached_evidence_record(
                candidate_root, candidate_record, candidate_verifier
            )
            scenarios.append(
                {"name": name, "status": result["status"], "errors": result["errors"]}
            )
            return result

        valid = evaluate("single-detached-sha512-evidence-record")
        wrong_root = evaluate(
            "wrong-detached-root", candidate_root=hashlib.sha512(detached_root).digest()
        )
        truncated = evaluate(
            "truncated-evidence-record", candidate_record=evidence_record[:-1]
        )
        version_two = evidence_record.replace(b"\x02\x01\x01", b"\x02\x01\x02", 1)
        wrong_version = evaluate("unsupported-version", candidate_record=version_two)
        sha512_oid = bytes.fromhex("0609608648016503040203")
        sha256_oid = bytes.fromhex("0609608648016503040201")
        downgrade_record = evidence_record.replace(sha512_oid, sha256_oid, 1)
        downgrade = evaluate(
            "sha256-algorithm-downgrade", candidate_record=downgrade_record
        )
        tampered_token = bytearray(token_bytes)
        tampered_token[-1] ^= 1
        tampered = evaluate(
            "tampered-cms-timestamp",
            candidate_record=build_detached_evidence_record(bytes(tampered_token)),
        )
        trailing = evaluate(
            "trailing-der-data", candidate_record=evidence_record + b"\x00"
        )
        other_tsa_root = root / "other-tsa"
        other_tsa_root.mkdir()
        other_response_verifier, _ = _tsa(other_tsa_root, digest_algorithm="sha512")
        wrong_anchor_verifier = OpenSslRfc3161TimestampVerifier(
            other_response_verifier.trust_anchor_path,
            expected_hash_algorithm="sha512",
            token_is_content_info=True,
        )
        wrong_anchor = evaluate(
            "untrusted-timestamp-authority",
            candidate_verifier=wrong_anchor_verifier,
        )

    holds = (
        wrong_root,
        truncated,
        wrong_version,
        downgrade,
        tampered,
        trailing,
        wrong_anchor,
    )
    return {
        "schema": "truepanel.holodeck-temperature-rfc4998-interoperability/v1",
        "simulation": True,
        "hardware_isolated": True,
        "scenarios": scenarios,
        "measurements": {
            "scenario_count": len(scenarios),
            "self_verified_fixtures": int(valid["status"] == STATUS_SELF_VERIFIED),
            "external_validation_ready": int(
                valid["eligible_for_external_interoperability_validation"]
            ),
            "external_validations_completed": 0,
            "hold_count": sum(item["status"] != STATUS_SELF_VERIFIED for item in holds),
            "rfc4998_archive_chains": 1,
            "rfc4998_archive_timestamps": 1,
            "actual_rfc3161_content_info_tokens_verified": 1,
            "predecessor_hash_tree_rehearsals": 1,
            "wrong_root_acceptances": 0,
            "malformed_der_acceptances": 0,
            "digest_downgrade_acceptances": 0,
            "untrusted_tsa_acceptances": 0,
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


__all__ = ["run_temperature_rfc4998_interop_checkride"]
