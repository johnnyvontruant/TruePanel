"""No-deploy, stdout-only observation of the passive AEGIS runtime gate."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from .passive_providers import TrueNASReadOnlyQueryClient
from .passive_runtime import (
    BoundedTrueNASQueryCache,
    GovernedPassiveEvidenceRuntime,
    GovernedRestoreReceiptStore,
)
from .passive_websocket import TrueNASWebSocketReadOnlyClient


def _sanitized_result(incident_id: str, result: dict[str, Any]) -> dict[str, Any]:
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


def observe(incident_id: str, receipt_root: Path) -> dict[str, Any]:
    client = BoundedTrueNASQueryCache(TrueNASReadOnlyQueryClient())
    runtime = GovernedPassiveEvidenceRuntime(
        client,
        GovernedRestoreReceiptStore(receipt_root),
    )
    return _sanitized_result(incident_id, runtime.observe(incident_id=incident_id))


def observe_websocket(
    incident_id: str,
    receipt_root: Path,
    *,
    uri: str,
    username: str,
    api_key_file: Path,
    tls_ca_file: Path | None = None,
    client_factory: Any | None = None,
) -> dict[str, Any]:
    with TrueNASWebSocketReadOnlyClient(
        uri=uri,
        username=username,
        api_key_file=api_key_file,
        tls_ca_file=tls_ca_file,
        client_factory=client_factory,
    ) as websocket_client:
        client = BoundedTrueNASQueryCache(websocket_client)
        runtime = GovernedPassiveEvidenceRuntime(
            client,
            GovernedRestoreReceiptStore(receipt_root),
        )
        result = _sanitized_result(
            incident_id,
            runtime.observe(incident_id=incident_id),
        )
        result["transport"] = websocket_client.status()
        return result


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Inspect the governed AEGIS passive-evidence gate without deployment"
    )
    parser.add_argument("--incident-id", required=True)
    parser.add_argument("--receipt-root", type=Path, required=True)
    parser.add_argument(
        "--websocket-uri",
        help="TLS-verified TrueNAS endpoint, for example wss://nas.example/api/current",
    )
    parser.add_argument(
        "--username",
        help="operator-created read-only TrueNAS service-account username",
    )
    parser.add_argument(
        "--api-key-file",
        type=Path,
        help="owner-only file containing the expiring API key; the key is never accepted in argv",
    )
    parser.add_argument(
        "--tls-ca-file",
        type=Path,
        help="optional governed PEM trust file used only by this observation process",
    )
    arguments = parser.parse_args(argv)

    websocket_values = (
        arguments.websocket_uri,
        arguments.username,
        arguments.api_key_file,
    )
    if any(value is not None for value in websocket_values) and not all(
        value is not None for value in websocket_values
    ):
        parser.error(
            "--websocket-uri, --username, and --api-key-file must be supplied together"
        )
    if arguments.tls_ca_file is not None and not all(
        value is not None for value in websocket_values
    ):
        parser.error("--tls-ca-file requires WebSocket mode")

    if all(value is not None for value in websocket_values):
        result = observe_websocket(
            arguments.incident_id,
            arguments.receipt_root,
            uri=arguments.websocket_uri,
            username=arguments.username,
            api_key_file=arguments.api_key_file,
            tls_ca_file=arguments.tls_ca_file,
        )
    else:
        result = observe(arguments.incident_id, arguments.receipt_root)

    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
