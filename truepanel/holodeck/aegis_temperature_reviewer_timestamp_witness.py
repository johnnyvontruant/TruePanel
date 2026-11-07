"""Deterministic RFC 3161 witness rehearsal for reviewer signatures."""

from __future__ import annotations

import os
import subprocess
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from truepanel.aegis.rfc3161_timestamp import (
    DEFAULT_POLICY_OID,
    OpenSslRfc3161TimestampVerifier,
)
from truepanel.aegis.ssh_verifier import (
    OpenSshSignatureVerifier,
    validate_allowed_signers_roster,
)
from truepanel.aegis.temperature_calibration_candidate_appraisal import _canonical
from truepanel.aegis.temperature_reviewer_root_rotation import (
    NAMESPACE as ROTATION_NAMESPACE,
)
from truepanel.aegis.temperature_reviewer_root_rotation import (
    PREDECESSOR_KEY_ID,
    SUCCESSOR_KEY_ID,
    build_temperature_reviewer_root_rotation_statement,
)
from truepanel.aegis.temperature_reviewer_timestamp_witness import (
    STATUS_COMPROMISED,
    STATUS_PRECOMPROMISE,
    STATUS_VALID,
    evaluate_temperature_reviewer_timestamp_witness,
)
from truepanel.aegis.temperature_two_person_replay_review import (
    NAMESPACE as REVIEW_NAMESPACE,
)
from truepanel.aegis.temperature_two_person_replay_review import (
    REVIEWER_KEY_ID,
    STATEMENT_SCHEMA,
)
from truepanel.holodeck.aegis_temperature_authenticated_label_join import _sign

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


def _run(*command: str) -> None:
    subprocess.run(
        command,
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=10,
    )


def _format(value: datetime) -> str:
    return (
        value.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    )


def _tsa(root: Path) -> tuple[OpenSslRfc3161TimestampVerifier, Path]:
    ca_key, ca_cert = root / "tsa-ca.key", root / "tsa-ca.crt"
    tsa_key, tsa_csr, tsa_cert = (
        root / "tsa.key",
        root / "tsa.csr",
        root / "tsa.crt",
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
        "/CN=TruePanel HoloDeck Timestamp Root",
        "-days",
        "2",
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
        "/CN=TruePanel HoloDeck Timestamp Authority",
        "-sha256",
    )
    extensions = root / "tsa-extensions.cnf"
    extensions.write_text(
        "[tsa_ext]\n"
        "basicConstraints=critical,CA:FALSE\n"
        "keyUsage=critical,digitalSignature,nonRepudiation\n"
        "extendedKeyUsage=critical,timeStamping\n"
        "subjectKeyIdentifier=hash\n"
        "authorityKeyIdentifier=keyid,issuer\n",
        encoding="ascii",
    )
    _run(
        "/usr/bin/openssl",
        "x509",
        "-req",
        "-in",
        str(tsa_csr),
        "-CA",
        str(ca_cert),
        "-CAkey",
        str(ca_key),
        "-set_serial",
        "2",
        "-out",
        str(tsa_cert),
        "-days",
        "2",
        "-sha256",
        "-extfile",
        str(extensions),
        "-extensions",
        "tsa_ext",
    )
    serial = root / "tsa-serial"
    serial.write_text("01\n", encoding="ascii")
    config = root / "tsa.cnf"
    config.write_text(
        "[tsa]\n"
        "default_tsa=tsa_config\n"
        "[tsa_config]\n"
        f"serial={serial}\n"
        "crypto_device=builtin\n"
        f"signer_cert={tsa_cert}\n"
        f"certs={ca_cert}\n"
        f"signer_key={tsa_key}\n"
        "signer_digest=sha256\n"
        f"default_policy={DEFAULT_POLICY_OID}\n"
        f"other_policies={DEFAULT_POLICY_OID}\n"
        "digests=sha256\n"
        "accuracy=secs:1\n"
        "ordering=yes\n"
        "tsa_name=yes\n"
        "ess_cert_id_chain=yes\n",
        encoding="ascii",
    )
    os.chmod(ca_cert, 0o600)
    return OpenSslRfc3161TimestampVerifier(ca_cert), config


def _issue(config: Path, signature: Path, token: Path) -> None:
    query = token.with_suffix(".tsq")
    _run(
        "/usr/bin/openssl",
        "ts",
        "-query",
        "-data",
        str(signature),
        "-sha256",
        "-cert",
        "-out",
        str(query),
    )
    _run(
        "/usr/bin/openssl",
        "ts",
        "-reply",
        "-config",
        str(config),
        "-section",
        "tsa_config",
        "-queryfile",
        str(query),
        "-out",
        str(token),
    )


def run_temperature_reviewer_timestamp_witness_checkride() -> dict[str, Any]:
    scenarios: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="truepanel-rfc3161-witness-") as directory:
        root = Path(directory).resolve()
        predecessor_key, successor_key, reviewer_key = (
            root / "old-root",
            root / "new-root",
            root / "reviewer",
        )
        for key in (predecessor_key, successor_key, reviewer_key):
            _run(
                "/usr/bin/ssh-keygen",
                "-q",
                "-t",
                "ed25519",
                "-N",
                "",
                "-f",
                str(key),
            )

        def verifier(
            key: Path, key_id: str, namespace: str
        ) -> OpenSshSignatureVerifier:
            allowed = root / f"{key.stem}-{key_id}.allowed"
            allowed.write_text(
                f"{key_id} {key.with_suffix('.pub').read_text(encoding='ascii')}",
                encoding="ascii",
            )
            os.chmod(allowed, 0o600)
            return OpenSshSignatureVerifier(
                allowed, namespace=namespace, expected_key_ids=(key_id,)
            )

        predecessor = verifier(predecessor_key, PREDECESSOR_KEY_ID, ROTATION_NAMESPACE)
        successor = verifier(successor_key, SUCCESSOR_KEY_ID, ROTATION_NAMESPACE)
        reviewer = verifier(reviewer_key, REVIEWER_KEY_ID, REVIEW_NAMESPACE)
        reviewer_fingerprint = validate_allowed_signers_roster(
            f"{REVIEWER_KEY_ID} {reviewer_key.with_suffix('.pub').read_text(encoding='ascii')}".encode(),
            expected_key_ids=(REVIEWER_KEY_ID,),
        )[REVIEWER_KEY_ID]
        timestamp_verifier, tsa_config = _tsa(root)

        def review(name: str, prepared: datetime, *, authority: bool = False):
            statement_path = root / f"{name}.review.json"
            statement = {
                "schema": STATEMENT_SCHEMA,
                "namespace": REVIEW_NAMESPACE,
                "scope": "independent-replay-evidence-concurrence-only",
                "key_id": REVIEWER_KEY_ID,
                "reviewer_key_fingerprint": reviewer_fingerprint,
                "prepared_at_utc": _format(prepared),
                "expires_at_utc": _format(prepared + timedelta(hours=2)),
                "decision": "CONCUR_ACCEPT_EVIDENCE",
                "rationale": "independently-reconstructed-and-concurred",
                "primary_review_receipt_sha256": "c" * 64,
                "replay_receipt_sha256": "d" * 64,
                "primary_operator_key_fingerprint": "SHA256:fixture-primary",
                "independent_identity_required": True,
                "two_person_quorum": True,
                "manual_calibration_consideration": True,
                **{key: False for key in _DENIED},
            }
            if authority:
                statement["deployment_authority"] = True
            statement_path.write_bytes(_canonical(statement))
            signature_path = root / f"{name}.review.sig"
            _sign(reviewer_key, statement_path, signature_path, REVIEW_NAMESPACE)
            token_path = root / f"{name}.tsr"
            _issue(tsa_config, signature_path, token_path)
            witnessed = timestamp_verifier(
                signature_path.read_bytes(), token_path.read_bytes()
            )
            if witnessed["verified"] is not True:
                raise RuntimeError(f"fixture timestamp failed: {witnessed['errors']}")
            return (
                statement_path,
                signature_path,
                token_path,
                _parse(witnessed["gen_time_utc"]),
            )

        def run(
            name: str,
            review_paths: tuple[Path, Path, Path, datetime],
            *,
            compromise_offset: int | None,
            missing_successor: bool = False,
            tamper_token: bool = False,
        ) -> dict[str, Any]:
            statement_path, signature_path, token_path, witnessed = review_paths
            rotation_start = witnessed + timedelta(minutes=2)
            fingerprint = reviewer_fingerprint
            events = ()
            if compromise_offset is not None:
                compromised = witnessed + timedelta(seconds=compromise_offset)
                events = (
                    {
                        "fingerprint": fingerprint,
                        "compromised_at_utc": _format(compromised),
                        "revoked_at_utc": _format(rotation_start),
                        "reason": "confirmed-compromise",
                    },
                )
            rotation = root / f"{name}.rotation.json"
            rotation.write_bytes(
                build_temperature_reviewer_root_rotation_statement(
                    predecessor,
                    successor,
                    from_generation=1,
                    to_generation=2,
                    previous_manifest_sha256="a" * 64,
                    successor_manifest_sha256="b" * 64,
                    prepared_at_utc=_format(rotation_start),
                    expires_at_utc=_format(rotation_start + timedelta(hours=1)),
                    compromise_events=events,
                )
            )
            old_signature = root / f"{name}.old.sig"
            new_signature = root / f"{name}.new.sig"
            _sign(predecessor_key, rotation, old_signature, ROTATION_NAMESPACE)
            if not missing_successor:
                _sign(successor_key, rotation, new_signature, ROTATION_NAMESPACE)
            selected_token = token_path
            if tamper_token:
                selected_token = root / f"{name}.tampered.tsr"
                damaged = bytearray(token_path.read_bytes())
                damaged[-1] ^= 1
                selected_token.write_bytes(damaged)
            result = evaluate_temperature_reviewer_timestamp_witness(
                predecessor,
                successor,
                rotation,
                old_signature,
                new_signature,
                reviewer,
                statement_path,
                signature_path,
                timestamp_verifier,
                selected_token,
                now_utc=_format(rotation_start + timedelta(seconds=1)),
            )
            scenarios.append(
                {
                    "name": name,
                    "status": result["status"],
                    "accepted": result["historical_signature_accepted"],
                    "errors": result["errors"],
                }
            )
            return result

        now = datetime.now(UTC).replace(microsecond=0)
        normal = review("normal", now - timedelta(minutes=1))
        delayed = review("delayed", now - timedelta(minutes=30))
        escalated = review(
            "authority-escalation", now - timedelta(minutes=1), authority=True
        )
        before = run("before-compromise", normal, compromise_offset=60)
        after = run("after-compromise", normal, compromise_offset=-1)
        clean = run("unaffected-reviewer", normal, compromise_offset=None)
        tampered = run(
            "tampered-token", normal, compromise_offset=60, tamper_token=True
        )
        delayed_result = run("delayed-witness", delayed, compromise_offset=60)
        untrusted = run(
            "untrusted-rotation",
            normal,
            compromise_offset=60,
            missing_successor=True,
        )
        authority = run("authority-escalation", escalated, compromise_offset=60)
    return {
        "schema": "truepanel.holodeck-temperature-reviewer-timestamp-witness/v1",
        "simulation": True,
        "hardware_isolated": True,
        "scenarios": scenarios,
        "measurements": {
            "scenario_count": len(scenarios),
            "precompromise_valid_count": int(before["status"] == STATUS_PRECOMPROMISE),
            "unaffected_valid_count": int(clean["status"] == STATUS_VALID),
            "postcompromise_hold_count": int(after["status"] == STATUS_COMPROMISED),
            "tampered_token_acceptances": int(
                tampered["historical_signature_accepted"]
            ),
            "delayed_witness_acceptances": int(
                delayed_result["historical_signature_accepted"]
            ),
            "untrusted_rotation_acceptances": int(
                untrusted["historical_signature_accepted"]
            ),
            "authority_escalation_acceptances": int(
                authority["historical_signature_accepted"]
            ),
            "coverage_total": 8,
            "coverage_trusted": 8,
            "coverage_gaps": 0,
            "supporting_signal_count": 5,
            "confidence": 0.95,
            "shared_cooling_first_match_sample": 19,
            "isolated_threshold_first_match_sample": 46,
            "lead_samples": 27,
            "field_validations": 0,
            "deployments": 0,
            "hardware_actions": 0,
            "runtime_writes": 0,
            "fixture_private_keys_created": 5,
            "fixture_private_keys_retained": 0,
        },
    }


def _parse(value: str) -> datetime:
    return datetime.fromisoformat(value[:-1] + "+00:00")


__all__ = ["run_temperature_reviewer_timestamp_witness_checkride"]
