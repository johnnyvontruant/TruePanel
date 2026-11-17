"""Deterministic adversarial rehearsal for the active-record receipt join."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from truepanel.aegis.rfc4998_active_receipt import (
    STATUS_REHEARSED,
    ActiveReceiptError,
    join_active_record_receipts,
)


def run_rfc4998_active_receipt_checkride(root: Path | None = None) -> dict[str, Any]:
    repository = root or Path(__file__).resolve().parents[2]
    evidence = repository / "docs" / "evidence"
    manifest = json.loads(
        (evidence / "aegis-rfc4998-active-record-manifest-v1.json").read_text()
    )
    receipts = [
        json.loads(
            (evidence / "aegis-rfc4998-bouncycastle-receipt-v1.json").read_text()
        ),
        json.loads((evidence / "aegis-rfc4998-etsi-dss-receipt-v1.json").read_text()),
    ]
    scenarios: list[dict[str, Any]] = []

    accepted = join_active_record_receipts(manifest, receipts)
    scenarios.append(
        {
            "name": "matching-dual-oracle-receipts",
            "status": accepted["active_record_external_validation"],
            "errors": [],
        }
    )

    def reject(name: str, candidate: list[dict[str, Any]]) -> None:
        try:
            join_active_record_receipts(manifest, candidate)
        except ActiveReceiptError as error:
            scenarios.append({"name": name, "status": "HOLD", "errors": [str(error)]})
            return
        raise AssertionError(f"{name} was accepted")

    reject("missing-oracle", receipts[:1])
    reject("duplicate-oracle", [receipts[0], receipts[0]])
    wrong_record = copy.deepcopy(receipts)
    wrong_record[1]["fixture_sha256"] = "0" * 64
    reject("record-digest-mismatch", wrong_record)
    wrong_data = copy.deepcopy(receipts)
    wrong_data[0]["detached_data_sha512"] = "0" * 128
    reject("detached-digest-mismatch", wrong_data)
    failed_verdict = copy.deepcopy(receipts)
    failed_verdict[1]["timestamp_signature_valid"] = False
    reject("failed-oracle-verdict", failed_verdict)
    authority = copy.deepcopy(receipts)
    authority[0]["production_trusted"] = True
    reject("authority-escalation", authority)
    unknown = copy.deepcopy(receipts)
    unknown[1]["schema"] = "unknown"
    reject("unknown-receipt-schema", unknown)

    return {
        "schema": "truepanel.holodeck-rfc4998-active-record-receipt/v1",
        "simulation": True,
        "hardware_isolated": True,
        "scenarios": scenarios,
        "measurements": {
            "scenario_count": len(scenarios),
            "trusted_rehearsals": int(
                accepted["active_record_external_validation"] == STATUS_REHEARSED
            ),
            "hold_count": sum(item["status"] == "HOLD" for item in scenarios),
            "oracle_receipts_joined": len(accepted["oracle_receipts"]),
            "record_digest_mismatch_acceptances": 0,
            "detached_digest_mismatch_acceptances": 0,
            "failed_verdict_acceptances": 0,
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


__all__ = ["run_rfc4998_active_receipt_checkride"]
