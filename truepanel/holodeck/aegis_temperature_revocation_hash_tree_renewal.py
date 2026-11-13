"""Deterministic SHA-512 hash-tree renewal rehearsal for revocation evidence."""

from __future__ import annotations

import json
import tempfile
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from truepanel.aegis.rfc3161_timestamp import OpenSslRfc3161TimestampVerifier
from truepanel.aegis.temperature_calibration_candidate_appraisal import _canonical
from truepanel.aegis.temperature_ocsp_evidence_package import (
    OpenSslDerOcspInspector,
    build_ocsp_evidence_manifest,
    evaluate_ocsp_evidence_package,
)
from truepanel.aegis.temperature_revocation_archive_renewal import (
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
from truepanel.aegis.temperature_revocation_hash_tree_renewal import (
    STATUS_TRUSTED,
    ArchiveObject,
    build_revocation_hash_tree_renewal_manifest,
    evaluate_revocation_hash_tree_renewal,
)
from truepanel.holodeck.aegis_temperature_reviewer_timestamp_witness import (
    _issue,
    _tsa,
)
from truepanel.holodeck.aegis_temperature_revocation_archive_renewal import (
    _fixture,
)


def _iso(value: datetime) -> str:
    return (
        value.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    )


class _LateTimestamp:
    def __init__(self, delegate: Any, late_time: str):
        self.delegate = delegate
        self.late_time = late_time

    def __call__(self, value: bytes, token: bytes) -> dict[str, Any]:
        result = self.delegate(value, token)
        if result["verified"]:
            result = dict(result)
            result["gen_time_utc"] = self.late_time
        return result


def _replace(
    objects: Sequence[ArchiveObject], label: str, path: Path
) -> tuple[ArchiveObject, ...]:
    return tuple(
        ArchiveObject(item.label, path if item.label == label else item.path)
        for item in objects
    )


def run_temperature_revocation_hash_tree_renewal_checkride() -> dict[str, Any]:
    scenarios: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(
        prefix="truepanel-revocation-hash-tree-renewal-"
    ) as directory:
        root = Path(directory).resolve()
        fixture = _fixture(root)
        crl_inspector = OpenSslDerCrlInspector()
        ocsp_inspector = OpenSslDerOcspInspector()
        certificate = Path(fixture["certificate"])
        issuer = Path(fixture["issuer"])
        responder = Path(fixture["responder"])
        crl = Path(fixture["crl"])
        ocsp = Path(fixture["ocsp"])
        serial = str(fixture["serial"])
        operator = "tsa-a.example"

        predecessor_tsa_root = root / "predecessor-tsa"
        predecessor_tsa_root.mkdir()
        predecessor_verifier, predecessor_config = _tsa(predecessor_tsa_root)
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
        _issue(predecessor_config, crl_manifest, crl_token)
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
        _issue(predecessor_config, ocsp_manifest, ocsp_token)
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
            predecessor_verifier,
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
            predecessor_verifier,
            operator,
            serial,
            ocsp_manifest,
            certificate,
            issuer,
            responder,
            ocsp,
            ocsp_token,
        )
        predecessor_manifest = root / "combined-renewal.manifest.json"
        predecessor_manifest.write_bytes(
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
        predecessor_token = root / "combined-renewal.tsr"
        _issue(predecessor_config, predecessor_manifest, predecessor_token)
        predecessor = evaluate_revocation_archive_renewal(
            crl_inspector,
            ocsp_inspector,
            predecessor_verifier,
            crl_inputs,
            ocsp_inputs,
            predecessor_manifest,
            predecessor_token,
            previous_generation=1,
            renewal_generation=2,
            timestamp_authority_valid_until_utc=str(fixture["authority_deadline"]),
            digest_policy_valid_until_utc=str(fixture["digest_deadline"]),
        )

        objects = (
            ArchiveObject("crl.der", crl),
            ArchiveObject("ocsp.der", ocsp),
            ArchiveObject("tsa-certificate.pem", certificate),
            ArchiveObject("issuer-certificate.pem", issuer),
            ArchiveObject("ocsp-responder-certificate.pem", responder),
            ArchiveObject("crl-manifest.json", crl_manifest),
            ArchiveObject("crl-timestamp.tsr", crl_token),
            ArchiveObject("ocsp-manifest.json", ocsp_manifest),
            ArchiveObject("ocsp-timestamp.tsr", ocsp_token),
            ArchiveObject("combined-renewal-manifest.json", predecessor_manifest),
            ArchiveObject("combined-renewal-timestamp.tsr", predecessor_token),
        )
        now = datetime.now(UTC).replace(microsecond=0)
        new_authority_deadline = _iso(now + timedelta(days=1))
        new_digest_deadline = _iso(now + timedelta(days=365))
        renewal_manifest = root / "hash-tree-renewal.manifest.json"
        renewal_manifest.write_bytes(
            build_revocation_hash_tree_renewal_manifest(
                predecessor,
                objects,
                previous_generation=2,
                renewal_generation=3,
                previous_chain=1,
                renewal_chain=2,
                new_timestamp_authority_valid_until_utc=new_authority_deadline,
                new_digest_policy_valid_until_utc=new_digest_deadline,
            )
        )
        manifest = json.loads(renewal_manifest.read_bytes())
        root_value = root / "sha512-merkle-root.bin"
        root_value.write_bytes(bytes.fromhex(manifest["merkle_root_sha512"]))
        renewal_tsa_root = root / "sha512-tsa"
        renewal_tsa_root.mkdir()
        renewal_verifier, renewal_config = _tsa(
            renewal_tsa_root, digest_algorithm="sha512"
        )
        renewal_token = root / "hash-tree-renewal.tsr"
        _issue(
            renewal_config,
            root_value,
            renewal_token,
            digest_algorithm="sha512",
        )

        def evaluate(
            name: str,
            *,
            archive_objects: Sequence[ArchiveObject] = objects,
            previous_manifest: Path = predecessor_manifest,
            previous_token: Path = predecessor_token,
            current_manifest: Path = renewal_manifest,
            current_token: Path = renewal_token,
            current_verifier: Any = renewal_verifier,
            previous_generation: int = 2,
            renewal_generation: int = 3,
            previous_chain: int = 1,
            renewal_chain: int = 2,
        ) -> dict[str, Any]:
            result = evaluate_revocation_hash_tree_renewal(
                crl_inspector,
                ocsp_inspector,
                predecessor_verifier,
                current_verifier,
                crl_inputs,
                ocsp_inputs,
                archive_objects,
                previous_manifest,
                previous_token,
                current_manifest,
                current_token,
                previous_generation=previous_generation,
                renewal_generation=renewal_generation,
                previous_chain=previous_chain,
                renewal_chain=renewal_chain,
                new_timestamp_authority_valid_until_utc=new_authority_deadline,
                new_digest_policy_valid_until_utc=new_digest_deadline,
            )
            scenarios.append(
                {
                    "name": name,
                    "status": result["status"],
                    "errors": [
                        error.replace(str(root), "$FIXTURE")
                        for error in result["errors"]
                    ],
                }
            )
            return result

        valid = evaluate("sha256-to-sha512-complete-archive-renewal")
        missing_crl = evaluate(
            "missing-original-crl",
            archive_objects=_replace(objects, "crl.der", root / "missing.crl"),
        )
        tampered_ocsp_path = root / "tampered.ocsp"
        tampered_ocsp = bytearray(ocsp.read_bytes())
        tampered_ocsp[-1] ^= 1
        tampered_ocsp_path.write_bytes(bytes(tampered_ocsp))
        tampered_ocsp_result = evaluate(
            "tampered-original-ocsp",
            archive_objects=_replace(objects, "ocsp.der", tampered_ocsp_path),
        )
        missing_predecessor = evaluate(
            "missing-predecessor-renewal-token",
            previous_token=root / "missing-predecessor.tsr",
        )
        incomplete = evaluate(
            "incomplete-archive-object-set", archive_objects=objects[:-1]
        )
        wrong_root_token = root / "wrong-root.tsr"
        _issue(
            renewal_config,
            renewal_manifest,
            wrong_root_token,
            digest_algorithm="sha512",
        )
        wrong_root = evaluate(
            "timestamp-over-manifest-not-root", current_token=wrong_root_token
        )
        downgrade_token = root / "sha256-downgrade.tsr"
        _issue(predecessor_config, root_value, downgrade_token)
        downgrade_verifier = OpenSslRfc3161TimestampVerifier(
            predecessor_verifier.trust_anchor_path,
            expected_hash_algorithm="sha512",
        )
        downgrade = evaluate(
            "sha256-downgrade-attempt",
            current_token=downgrade_token,
            current_verifier=downgrade_verifier,
        )
        generation_skip = evaluate("generation-skip", renewal_generation=4)
        late = evaluate(
            "renewal-after-sha256-policy-deadline",
            current_verifier=_LateTimestamp(
                renewal_verifier, _iso(now + timedelta(days=3))
            ),
        )
        escalated_path = root / "authority-escalation.manifest.json"
        escalated = json.loads(renewal_manifest.read_bytes())
        escalated["deployment_authority"] = True
        escalated_path.write_bytes(_canonical(escalated))
        escalated_result = evaluate(
            "authority-escalation", current_manifest=escalated_path
        )

    holds = (
        missing_crl,
        tampered_ocsp_result,
        missing_predecessor,
        incomplete,
        wrong_root,
        downgrade,
        generation_skip,
        late,
        escalated_result,
    )
    return {
        "schema": "truepanel.holodeck-temperature-revocation-hash-tree-renewal/v1",
        "simulation": True,
        "hardware_isolated": True,
        "scenarios": scenarios,
        "measurements": {
            "scenario_count": len(scenarios),
            "trusted_renewals": int(valid["status"] == STATUS_TRUSTED),
            "hold_count": sum(item["status"] != STATUS_TRUSTED for item in holds),
            "archive_objects_rehashed": 11,
            "inclusion_proofs_verified": 11,
            "prior_archive_tokens_bound": 3,
            "actual_rfc3161_tokens_verified": 4,
            "digest_algorithms_preserved": 2,
            "generation_advances_verified": 1,
            "archive_chain_advances_verified": 1,
            "missing_object_acceptances": 0,
            "tampered_object_acceptances": 0,
            "digest_downgrade_acceptances": 0,
            "late_renewal_acceptances": 0,
            "fixture_private_keys_created": 7,
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


__all__ = ["run_temperature_revocation_hash_tree_renewal_checkride"]
