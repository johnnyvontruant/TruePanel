"""Content-bound public action packets for the AEGIS operator ceremony.

The packet explains one already-determined JT action.  It cannot satisfy the
action, manufacture independent delivery, accept a private key, or widen the
development-only authority boundary.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from .acceptance import semantic_sha256
from .field_ceremony import FIELD_CEREMONY_SCHEMA
from .verifier_bootstrap import verify_verifier_release

ACTION_PACKET_SCHEMA = "truepanel.aegis-development-operator-action-packet/v1"
ACTION_PACKET_STATUS = "READY_FOR_OPERATOR_ACTION"

_AUTHORITY = {
    "production_authority": False,
    "deployment_authority": False,
    "hardware_authority": False,
    "storage_write_authority": False,
    "automatic_promotion": False,
}

_ACTIONS: dict[str, dict[str, Any]] = {
    "ACTION_REQUIRED_INDEPENDENT_VERIFIER_CONFIRMATION": {
        "required_public_input": "INDEPENDENTLY_OBTAINED_VERIFIER_SHA256",
        "independent_channel_required": True,
        "operator_steps": [
            "Obtain the reviewed verifier SHA-256 through a JT-controlled channel.",
            "Compare that value with the content-pinned verifier SHA-256 on this card.",
            "Confirm only an exact match; this packet is not the independent source.",
        ],
    },
    "ACTION_REQUIRED_PUBLIC_ROSTER": {
        "required_public_input": "JT_ED25519_PUBLIC_KEY_AND_FINGERPRINT",
        "independent_channel_required": True,
        "operator_steps": [
            "Keep the private key outside TruePanel.",
            "Independently confirm the Ed25519 public-key fingerprint.",
            "Provision only the protected jt-development-review public roster.",
        ],
    },
    "ACTION_REQUIRED_SIGNING_KIT_EXPORT": {
        "required_public_input": "PINNED_CANDIDATE_CHECKOUT",
        "independent_channel_required": False,
        "operator_steps": [
            "Use the exact clean candidate checkout and operator-confirmed UTC.",
            "Export the public-only signing kit outside the checkout.",
            "Do not provide a private-key path or invoke a signer through TruePanel.",
        ],
    },
    "ACTION_REQUIRED_INDEPENDENT_KIT_AUDIT": {
        "required_public_input": "STANDALONE_AUDIT_WITNESS",
        "independent_channel_required": True,
        "operator_steps": [
            "Run the independently pinned standalone auditor against the exact kit.",
            "Preserve its canonical witness outside the kit.",
            "Continue only when both audit implementations agree exactly.",
        ],
    },
    "ACTION_REQUIRED_OFFLINE_SIGNATURE": {
        "required_public_input": "DETACHED_DEVELOPMENT_SSHSIG",
        "independent_channel_required": False,
        "operator_steps": [
            "Review the human card and canonical development signing session.",
            "Sign the canonical session outside TruePanel with JT's protected key.",
            "Return only the detached development SSHSIG for read-only verification.",
        ],
    },
}


def _canonical(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        dict(value), sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()


def _read_snapshot(path: str | Path, *, maximum_bytes: int = 1_048_576) -> bytes:
    value = Path(path)
    if not value.is_absolute() or value.is_symlink() or not value.is_file():
        raise ValueError("OperatorActionPacketInputUnsafe")
    try:
        if value.resolve(strict=True) != value:
            raise ValueError("OperatorActionPacketInputUnsafe")
        before = value.stat()
        if before.st_size <= 0 or before.st_size > maximum_bytes:
            raise ValueError("OperatorActionPacketInputUnsafe")
        content = value.read_bytes()
        after = value.stat()
    except OSError as error:
        raise ValueError("OperatorActionPacketInputUnavailable") from error
    def identity(item: Any) -> tuple[int, ...]:
        return (
            item.st_dev,
            item.st_ino,
            item.st_mode,
            item.st_size,
            item.st_mtime_ns,
            item.st_ctime_ns,
        )
    if not content or len(content) > maximum_bytes or identity(before) != identity(after):
        raise ValueError("OperatorActionPacketInputChanged")
    return content


def _sha256_file(path: str | Path) -> str:
    return hashlib.sha256(_read_snapshot(path)).hexdigest()


def build_operator_action_packet(
    *,
    ceremony_result: Mapping[str, Any],
    verifier_receipt_path: str | Path,
    verifier_source_path: str | Path,
) -> dict[str, Any]:
    """Build one deterministic public packet for an unsatisfied operator gate."""

    result = dict(ceremony_result)
    action = _ACTIONS.get(str(result.get("status")))
    stages = result.get("completed_stages")
    if (
        result.get("schema") != FIELD_CEREMONY_SCHEMA
        or action is None
        or not isinstance(stages, list)
        or result.get("scope") != "DEVELOPMENT_ONLY"
        or any(result.get(field) is not expected for field, expected in _AUTHORITY.items())
        or result.get("private_key_accepted") is not False
        or result.get("signer_invoked") is not False
        or result.get("runtime_writes") != 0
    ):
        raise ValueError("OperatorActionPacketCeremonyInvalid")

    release = verify_verifier_release(
        receipt_path=verifier_receipt_path,
        source_path=verifier_source_path,
    )
    if not stages or stages[0].get("source_sha256") != release["source_sha256"]:
        raise ValueError("OperatorActionPacketVerifierMismatch")

    return {
        "schema": ACTION_PACKET_SCHEMA,
        "status": ACTION_PACKET_STATUS,
        "action_status": result["status"],
        "next_action": result.get("next_action"),
        "operator_id": "jt",
        "ceremony_sha256": semantic_sha256(result),
        "completed_stages_sha256": hashlib.sha256(
            json.dumps(stages, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
        "verifier_source_sha256": release["source_sha256"],
        "verifier_release_receipt_sha256": _sha256_file(verifier_receipt_path),
        "required_public_input": action["required_public_input"],
        "operator_steps": list(action["operator_steps"]),
        "independent_channel_required": action["independent_channel_required"],
        "independent_channel_verified": False,
        "private_key_requested": False,
        "scope": "DEVELOPMENT_ONLY",
        **_AUTHORITY,
    }


def operator_action_packet_sha256(packet: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical(packet)).hexdigest()


def render_operator_action_card(packet: Mapping[str, Any]) -> str:
    """Render a deterministic card; the canonical packet remains authoritative."""

    steps = packet.get("operator_steps")
    if (
        packet.get("schema") != ACTION_PACKET_SCHEMA
        or packet.get("status") != ACTION_PACKET_STATUS
        or not isinstance(steps, Sequence)
        or isinstance(steps, (str, bytes))
    ):
        raise ValueError("OperatorActionPacketInvalid")
    lines = [
        "AEGIS DEVELOPMENT-ONLY OPERATOR ACTION",
        "",
        f"Action: {packet.get('action_status')}",
        f"Required public input: {packet.get('required_public_input')}",
        f"Verifier SHA-256: {packet.get('verifier_source_sha256')}",
        f"Packet SHA-256: {operator_action_packet_sha256(packet)}",
        "",
        "JT STEPS",
    ]
    lines.extend(f"  {index}. {step}" for index, step in enumerate(steps, 1))
    lines.extend(
        [
            "",
            "BOUNDARY",
            "  This packet is not an independent trust source.",
            "  Never provide a private key to TruePanel.",
            "  Production, deployment, hardware, and storage authority: NO.",
            "",
        ]
    )
    return "\n".join(lines)


def verify_operator_action_packet(
    *,
    packet: Mapping[str, Any],
    ceremony_result: Mapping[str, Any],
    verifier_receipt_path: str | Path,
    verifier_source_path: str | Path,
) -> dict[str, Any]:
    """Reconstruct and compare the packet without satisfying its action."""

    try:
        expected = build_operator_action_packet(
            ceremony_result=ceremony_result,
            verifier_receipt_path=verifier_receipt_path,
            verifier_source_path=verifier_source_path,
        )
    except ValueError as error:
        return {"status": "HOLD", "reason": str(error), **_AUTHORITY}
    if dict(packet) != expected:
        return {"status": "HOLD", "reason": "OperatorActionPacketMismatch", **_AUTHORITY}
    return {
        "status": "OPERATOR_ACTION_PACKET_VERIFIED",
        "action_status": expected["action_status"],
        "packet_sha256": operator_action_packet_sha256(expected),
        "action_satisfied": False,
        "independent_channel_verified": False,
        "private_key_accepted": False,
        "signer_invoked": False,
        "scope": "DEVELOPMENT_ONLY",
        **_AUTHORITY,
    }


def main(arguments: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build a public AEGIS operator action packet"
    )
    parser.add_argument("--ceremony-result", required=True, type=Path)
    parser.add_argument("--verifier-receipt", required=True, type=Path)
    parser.add_argument("--verifier-source", required=True, type=Path)
    values = parser.parse_args(arguments)
    try:
        ceremony = json.loads(_read_snapshot(values.ceremony_result))
        packet = build_operator_action_packet(
            ceremony_result=ceremony,
            verifier_receipt_path=values.verifier_receipt,
            verifier_source_path=values.verifier_source,
        )
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(json.dumps({"status": "HOLD", "reason": str(error)}, sort_keys=True))
        return 2
    print(json.dumps(packet, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "ACTION_PACKET_SCHEMA",
    "ACTION_PACKET_STATUS",
    "build_operator_action_packet",
    "operator_action_packet_sha256",
    "render_operator_action_card",
    "verify_operator_action_packet",
]
