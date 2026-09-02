"""No-deploy, stdout-only observation of the passive AEGIS runtime gate."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from .passive_providers import TrueNASReadOnlyQueryClient
from .passive_runtime import (
    BoundedTrueNASQueryCache,
    GovernedPassiveEvidenceRuntime,
    GovernedRestoreReceiptStore,
)


def observe(incident_id: str, receipt_root: Path) -> dict:
    client = BoundedTrueNASQueryCache(TrueNASReadOnlyQueryClient())
    runtime = GovernedPassiveEvidenceRuntime(
        client,
        GovernedRestoreReceiptStore(receipt_root),
    )
    result = runtime.observe(incident_id=incident_id)
    return {
        "schema_version": 1,
        "operation": "passive_no_deploy_observation",
        "incident_id": incident_id,
        "runtime_status": result.get("runtime_status"),
        "role_verification": result.get("role_verification"),
        "receipt_store": result.get("receipt_store"),
        "cache": result.get("cache"),
        "successful_tasks": result.get("successful_tasks", 0),
        "restore_verified": result.get("restore_verified") is True,
        "hold_reason": result.get("hold_reason"),
        "read_only": True,
        "control_authority": False,
        "deployment_changed": False,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Inspect the governed AEGIS passive-evidence gate without deployment"
    )
    parser.add_argument("--incident-id", required=True)
    parser.add_argument("--receipt-root", type=Path, required=True)
    arguments = parser.parse_args(argv)
    print(
        json.dumps(
            observe(arguments.incident_id, arguments.receipt_root),
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
