"""Sanitized no-deploy observation through a least-privilege API-key session."""

from __future__ import annotations

import argparse
import json
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from .credential_session import CredentialSafeTrueNASClient
from .passive_runtime import (
    BoundedTrueNASQueryCache,
    GovernedPassiveEvidenceRuntime,
    GovernedRestoreReceiptStore,
)


def observe_authenticated(
    incident_id: str,
    receipt_root: Path,
    *,
    api_uri: str,
    api_key_file: Path,
    client_factory: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    session: CredentialSafeTrueNASClient | None = None
    try:
        session = CredentialSafeTrueNASClient(
            api_uri,
            api_key_file,
            client_factory=client_factory,
        )
        client = BoundedTrueNASQueryCache(session)
        runtime = GovernedPassiveEvidenceRuntime(
            client,
            GovernedRestoreReceiptStore(receipt_root),
        )
        result = runtime.observe(incident_id=incident_id)
        session_state = session.status()
    except (OSError, RuntimeError, TypeError, ValueError, AttributeError):
        result = {
            "runtime_status": "HOLD",
            "restore_verified": False,
            "hold_reason": "credential-safe TrueNAS session unavailable",
        }
        session_state = session.status() if session is not None else {
            "transport": "rejected",
            "tls_certificate_verification": False,
            "required_transport": "wss_with_certificate_verification",
            "authenticated": False,
            "read_only": True,
            "control_authority": False,
        }
    finally:
        if session is not None:
            session.close()
    return {
        "schema_version": 1,
        "operation": "credential_safe_passive_observation",
        "incident_id": incident_id,
        "runtime_status": result.get("runtime_status", "HOLD"),
        "role_verification": result.get("role_verification"),
        "receipt_store": result.get("receipt_store"),
        "cache": result.get("cache"),
        "session": session_state,
        "successful_tasks": result.get("successful_tasks", 0),
        "restore_verified": result.get("restore_verified") is True,
        "hold_reason": result.get("hold_reason"),
        "read_only": True,
        "control_authority": False,
        "deployment_changed": False,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Inspect AEGIS through a certificate-verified, least-privilege "
            "TrueNAS API-key session without deployment"
        )
    )
    parser.add_argument("--incident-id", required=True)
    parser.add_argument("--receipt-root", type=Path, required=True)
    parser.add_argument("--api-uri", required=True)
    parser.add_argument("--api-key-file", type=Path, required=True)
    arguments = parser.parse_args(argv)
    print(
        json.dumps(
            observe_authenticated(
                arguments.incident_id,
                arguments.receipt_root,
                api_uri=arguments.api_uri,
                api_key_file=arguments.api_key_file,
            ),
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
