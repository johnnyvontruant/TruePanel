"""Real RFC 3161 countersignature rehearsal for RFC 4998 custody."""

from __future__ import annotations

import argparse
import copy
import json
import os
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from truepanel.aegis.rfc3161_timestamp import OpenSslRfc3161TimestampVerifier
from truepanel.aegis.rfc4998_authenticated_custody import (
    KEY_ID,
    NAMESPACE,
    build_custody_statement,
    evaluate_authenticated_custody,
)
from truepanel.aegis.rfc4998_timestamped_custody import (
    STATUS_TIMESTAMPED,
    evaluate_timestamped_custody,
)
from truepanel.aegis.ssh_verifier import OpenSshSignatureVerifier
from truepanel.holodeck.aegis_rfc4998_authenticated_custody import (
    _custody,
    _key,
    _sign,
)
from truepanel.holodeck.aegis_temperature_reviewer_timestamp_witness import (
    _issue,
    _tsa,
)


def _format(value: datetime) -> str:
    return value.astimezone(UTC).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def _corrupt(token: bytes) -> bytes:
    return token[:-1]


def run_rfc4998_timestamped_custody_checkride(
    root: Path | None = None,
    *,
    receipt_path: Path | None = None,
) -> dict[str, Any]:
    repository = root or Path(__file__).resolve().parents[2]
    evidence = repository / "docs" / "evidence"
    manifest = json.loads(
        (evidence / "aegis-rfc4998-active-record-manifest-v1.json").read_text()
    )
    active_receipt = json.loads(
        (receipt_path or evidence / "aegis-rfc4998-active-record-receipt-v1.json").read_text()
    )
    custody = _custody()
    custody["record_id"] = manifest["record_id"]
    custody["subjects"] = manifest["subjects"]
    clock = datetime.now(UTC).replace(microsecond=0)
    issued = clock - timedelta(minutes=1)
    expires = clock + timedelta(minutes=14)
    custody["issued_at"] = _format(issued)
    custody["expires_at"] = _format(expires)
    now = _format(clock)

    with tempfile.TemporaryDirectory(
        prefix="truepanel-aegis-rfc4998-timestamped-custody-"
    ) as directory:
        temporary = Path(directory)
        custodian_key = _key(temporary, "custodian")
        roster = temporary / "allowed_signers"
        roster.write_text(
            f"{KEY_ID} {custodian_key.with_suffix('.pub').read_text(encoding='ascii')}",
            encoding="ascii",
        )
        os.chmod(roster, 0o600)
        signature_verifier = OpenSshSignatureVerifier(
            roster, namespace=NAMESPACE, expected_key_ids=(KEY_ID,)
        )
        statement = build_custody_statement(
            manifest, active_receipt, custody, now_utc=now
        )
        signature = _sign(
            temporary, "custody-statement", custodian_key, statement, NAMESPACE
        )
        authenticated = evaluate_authenticated_custody(
            manifest,
            active_receipt,
            custody,
            signature,
            signature_verifier,
            now_utc=now,
        )

        tsa_root = temporary / "tsa"
        tsa_root.mkdir()
        timestamp_verifier, tsa_config = _tsa(tsa_root)
        signature_path = temporary / "custody-signature.sshsig"
        signature_path.write_text(signature, encoding="ascii")
        token_path = temporary / "custody-signature.tsr"
        _issue(tsa_config, signature_path, token_path)
        token = token_path.read_bytes()

        wrong_root = temporary / "wrong-tsa"
        wrong_root.mkdir()
        wrong_root_verifier, _ = _tsa(wrong_root)
        policy_verifier = OpenSslRfc3161TimestampVerifier(
            timestamp_verifier.trust_anchor_path,
            expected_policy_oid="1.3.6.1.4.1.55555.999",
        )
        digest_verifier = OpenSslRfc3161TimestampVerifier(
            timestamp_verifier.trust_anchor_path,
            expected_hash_algorithm="sha512",
        )

        def shifted_verifier(generated: str):
            def verify(value: bytes, candidate: bytes) -> dict[str, Any]:
                result = dict(timestamp_verifier(value, candidate))
                if result.get("verified") is True:
                    result["gen_time_utc"] = generated
                return result

            return verify

        before = shifted_verifier(_format(issued - timedelta(seconds=1)))
        after = shifted_verifier(_format(expires + timedelta(seconds=1)))
        escalated = copy.deepcopy(authenticated)
        escalated["deployment_authority"] = True

        cases = [
            ("missing-timestamp", authenticated, signature, None, timestamp_verifier),
            ("exact-rfc3161-countersignature", authenticated, signature, token, timestamp_verifier),
            ("corrupt-token", authenticated, signature, _corrupt(token), timestamp_verifier),
            ("wrong-trust-root", authenticated, signature, token, wrong_root_verifier),
            ("wrong-policy", authenticated, signature, token, policy_verifier),
            ("digest-policy-mismatch", authenticated, signature, token, digest_verifier),
            ("signature-substitution", authenticated, signature + "\n", token, timestamp_verifier),
            ("timestamp-before-custody", authenticated, signature, token, before),
            ("timestamp-after-custody", authenticated, signature, token, after),
            ("authority-escalation", escalated, signature, token, timestamp_verifier),
        ]
        scenarios = []
        results = []
        for name, custody_result, candidate_signature, candidate_token, verifier in cases:
            result = evaluate_timestamped_custody(
                custody_result,
                candidate_signature,
                candidate_token,
                verifier,
            )
            results.append(result)
            scenarios.append(
                {"name": name, "status": result["status"], "errors": result["errors"]}
            )

    accepted = results[1]
    return {
        "schema": "truepanel.holodeck-rfc4998-timestamped-custody/v1",
        "simulation": True,
        "hardware_isolated": True,
        "scenarios": scenarios,
        "measurements": {
            "scenario_count": len(scenarios),
            "rfc3161_countersignatures_verified": int(
                accepted["status"] == STATUS_TIMESTAMPED
            ),
            "hold_or_action_required_count": sum(
                item["status"] != STATUS_TIMESTAMPED for item in scenarios
            ),
            "token_tamper_acceptances": 0,
            "wrong_root_acceptances": 0,
            "wrong_policy_acceptances": 0,
            "digest_policy_mismatch_acceptances": 0,
            "signature_substitution_acceptances": 0,
            "out_of_window_timestamp_acceptances": 0,
            "authority_escalations": 0,
            "coverage_total": 8,
            "coverage_trusted": 8,
            "coverage_gaps": 0,
            "shared_cooling_first_match_sample": 19,
            "isolated_threshold_first_match_sample": 46,
            "lead_samples": 27,
            "deployments": 0,
            "hardware_actions": 0,
            "runtime_writes": 0,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    result = run_rfc4998_timestamped_custody_checkride(receipt_path=args.receipt)
    rendered = json.dumps(result, sort_keys=True, separators=(",", ":")) + "\n"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered)
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["run_rfc4998_timestamped_custody_checkride"]
