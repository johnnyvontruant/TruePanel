"""Operator-bound chassis identity verification for Preflight.

Some QNAP systems expose generic OEM DMI strings rather than the chassis
manufacturer.  This module lets an operator attest a known ambiguous hardware
profile without weakening unrelated compatibility checks or hardware-control
gates.

The receipt is metadata only.  It is bound to a privacy-safe fingerprint of
non-serial DMI identity fields and is ignored when those fields change.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from pathlib import Path
from typing import Any

CHASSIS_VERIFICATION_SCHEMA_VERSION = 1
DEFAULT_CHASSIS_VERIFICATION_PATH = Path(
    "/var/lib/truepanel/compatibility/chassis-identity.json"
)

_DMI_FIELDS = (
    "vendor",
    "product",
    "version",
    "board_vendor",
    "board",
)

_KNOWN_AMBIGUOUS_PROFILES = {
    ("INSYDE", "QW56"): "TVS-671",
}


def _read_text(path: Path) -> str:
    try:
        return path.read_text(
            encoding="utf-8",
            errors="replace",
        ).strip()
    except (
        FileNotFoundError,
        PermissionError,
        IsADirectoryError,
        OSError,
    ):
        return ""


def read_dmi_identity(
    root: str | Path = "/",
) -> dict[str, str]:
    root_path = Path(root)
    dmi = root_path / "sys/class/dmi/id"

    return {
        "vendor": _read_text(dmi / "sys_vendor"),
        "product": _read_text(dmi / "product_name"),
        "version": _read_text(dmi / "product_version"),
        "board_vendor": _read_text(dmi / "board_vendor"),
        "board": _read_text(dmi / "board_name"),
    }


def identity_detail(values: dict[str, Any]) -> str:
    parts = [
        str(values.get(key) or "").strip()
        for key in ("vendor", "product")
    ]
    return " / ".join(
        part for part in parts if part
    ) or "DMI identity unavailable"


def chassis_fingerprint(values: dict[str, Any]) -> str:
    material = {
        key: str(values.get(key) or "").strip().lower()
        for key in _DMI_FIELDS
    }
    encoded = json.dumps(
        material,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def candidate_model(
    values: dict[str, Any],
) -> str | None:
    key = (
        str(values.get("vendor") or "").strip().upper(),
        str(values.get("product") or "").strip().upper(),
    )
    return _KNOWN_AMBIGUOUS_PROFILES.get(key)


def verification_matches(
    values: dict[str, Any],
    verification: dict[str, Any] | None,
) -> bool:
    if not isinstance(verification, dict):
        return False

    if verification.get("schema_version") != CHASSIS_VERIFICATION_SCHEMA_VERSION:
        return False

    if verification.get("state") != "verified":
        return False

    model = str(verification.get("model") or "").strip().upper()
    if not model:
        return False

    expected_model = candidate_model(values)
    if expected_model is None or model != expected_model.upper():
        return False

    return str(
        verification.get("fingerprint") or ""
    ) == chassis_fingerprint(values)


class ChassisIdentityStore:
    """Persist one operator chassis attestation bound to current DMI identity."""

    def __init__(
        self,
        path: str | Path | None = None,
        *,
        clock=None,
    ) -> None:
        self.path = Path(
            path or DEFAULT_CHASSIS_VERIFICATION_PATH
        )
        self.clock = clock or time.time
        self._lock = threading.RLock()

    def _load(self) -> dict[str, Any] | None:
        try:
            payload = json.loads(
                self.path.read_text(
                    encoding="utf-8"
                )
            )
        except (
            FileNotFoundError,
            OSError,
            TypeError,
            ValueError,
        ):
            return None

        return payload if isinstance(payload, dict) else None

    def current(
        self,
        *,
        root: str | Path = "/",
    ) -> dict[str, Any] | None:
        values = read_dmi_identity(root)

        with self._lock:
            payload = self._load()

        if verification_matches(values, payload):
            return dict(payload)

        return None

    def review(
        self,
        *,
        root: str | Path = "/",
    ) -> dict[str, Any]:
        values = read_dmi_identity(root)
        candidate = candidate_model(values)

        with self._lock:
            raw = self._load()

        current = (
            dict(raw)
            if verification_matches(values, raw)
            else None
        )

        return {
            "detected_identity": identity_detail(values),
            "confirmable": bool(
                candidate is not None
                and current is None
            ),
            "candidate_model": candidate,
            "verified": current is not None,
            "verified_model": (
                str(current.get("model") or "")
                if current is not None
                else None
            ),
            "binding": "current_hardware_fingerprint",
            "previous_verification_invalidated": bool(
                raw is not None
                and current is None
            ),
        }

    def confirm(
        self,
        *,
        model: str,
        root: str | Path = "/",
    ) -> dict[str, Any]:
        values = read_dmi_identity(root)
        expected = candidate_model(values)
        requested = str(model or "").strip().upper()

        if expected is None:
            raise ValueError(
                "Current DMI identity is not a known operator-confirmable QNAP profile."
            )

        if requested != expected.upper():
            raise ValueError(
                "Requested chassis model does not match the known DMI profile."
            )

        payload = {
            "schema_version": CHASSIS_VERIFICATION_SCHEMA_VERSION,
            "state": "verified",
            "model": expected,
            "fingerprint": chassis_fingerprint(values),
            "detected_vendor": str(values.get("vendor") or ""),
            "detected_product": str(values.get("product") or ""),
            "confirmed_at": float(self.clock()),
            "source": "operator_attestation",
            "hardware_control_granted": False,
        }

        encoded = json.dumps(
            payload,
            indent=2,
            sort_keys=True,
        ) + "\n"

        with self._lock:
            self.path.parent.mkdir(
                parents=True,
                exist_ok=True,
            )
            temporary = self.path.with_name(
                f".{self.path.name}.tmp-{os.getpid()}"
            )
            try:
                temporary.write_text(
                    encoded,
                    encoding="utf-8",
                )
                os.chmod(temporary, 0o600)
                os.replace(
                    temporary,
                    self.path,
                )
            finally:
                try:
                    temporary.unlink()
                except FileNotFoundError:
                    pass

        return dict(payload)


__all__ = [
    "CHASSIS_VERIFICATION_SCHEMA_VERSION",
    "ChassisIdentityStore",
    "candidate_model",
    "chassis_fingerprint",
    "identity_detail",
    "read_dmi_identity",
    "verification_matches",
]
