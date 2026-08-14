"""Simulation-only compatibility replay for privacy-safe support bundles."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

from .black_box import BlackBoxFrame, sanitize_black_box_value


COMPATIBILITY_REPLAY_SCHEMA_VERSION = 1
SUPPORT_BUNDLE_SCHEMA_VERSION = 1
MAX_SUPPORT_BUNDLE_BYTES = 1_048_576

_REQUIRED_PRIVACY = {
    "hostname": "excluded",
    "ip_addresses": "excluded",
    "serial_numbers": "excluded",
    "wwids": "excluded",
    "mac_addresses": "excluded",
    "usernames": "excluded",
    "configuration_secrets": "excluded",
    "pool_contents": "excluded",
}
_EXPECTED_TOP_LEVEL_KEYS = {
    "schema_version",
    "truepanel_version",
    "generated_at",
    "privacy",
    "compatibility",
}
_EXPECTED_COMPATIBILITY_KEYS = {
    "classification",
    "installation_mode",
    "hardware_control",
    "checks",
}
_EXPECTED_CHECK_KEYS = {"status", "name", "detail"}


def _require_mapping(value: Any, *, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _require_exact_keys(
    value: Mapping[str, Any],
    expected: set[str],
    *,
    label: str,
) -> None:
    actual = {str(key) for key in value}
    if actual != expected:
        missing = sorted(expected - actual)
        unexpected = sorted(actual - expected)
        raise ValueError(
            f"{label} fields do not match schema; "
            f"missing={missing}, unexpected={unexpected}"
        )


def _require_text(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string")
    return value.strip()


def _validate_generated_at(value: Any) -> str:
    generated_at = _require_text(value, label="generated_at")
    try:
        parsed = datetime.fromisoformat(generated_at)
    except ValueError as error:
        raise ValueError("generated_at must be ISO-8601") from error
    if parsed.tzinfo is None:
        raise ValueError("generated_at must include a timezone")
    return generated_at


def _validate_privacy(payload: Mapping[str, Any]) -> None:
    privacy = _require_mapping(payload.get("privacy"), label="privacy")
    if dict(privacy) != _REQUIRED_PRIVACY:
        raise ValueError(
            "support bundle privacy contract is incomplete or changed"
        )

    replay_source = {
        key: value
        for key, value in payload.items()
        if key != "privacy"
    }
    if sanitize_black_box_value(replay_source) != replay_source:
        raise ValueError(
            "support bundle contains data requiring privacy redaction"
        )


@dataclass(frozen=True)
class CompatibilityReplayCheck:
    """One passive compatibility observation prepared for simulation."""

    status: str
    name: str
    detail: str

    def as_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True)
class CompatibilityReplayProfile:
    """Validated, read-only machine profile derived from a support bundle."""

    source_schema_version: int
    source_truepanel_version: str
    source_generated_at: str
    classification: str
    installation_mode: str
    hardware_control: str
    checks: tuple[CompatibilityReplayCheck, ...]
    replay_schema_version: int = COMPATIBILITY_REPLAY_SCHEMA_VERSION
    privacy: str = "verified-support-bundle"
    simulation_only: bool = True

    @classmethod
    def from_support_bundle(
        cls,
        payload: Mapping[str, Any],
    ) -> "CompatibilityReplayProfile":
        source = _require_mapping(payload, label="support bundle")
        _require_exact_keys(
            source,
            _EXPECTED_TOP_LEVEL_KEYS,
            label="support bundle",
        )

        schema_version = source.get("schema_version")
        if schema_version != SUPPORT_BUNDLE_SCHEMA_VERSION:
            raise ValueError(
                "unsupported compatibility support bundle schema: "
                f"{schema_version}"
            )

        _validate_privacy(source)

        compatibility = _require_mapping(
            source.get("compatibility"),
            label="compatibility",
        )
        _require_exact_keys(
            compatibility,
            _EXPECTED_COMPATIBILITY_KEYS,
            label="compatibility",
        )

        raw_checks = compatibility.get("checks")
        if not isinstance(raw_checks, list):
            raise ValueError("compatibility checks must be a list")

        checks: list[CompatibilityReplayCheck] = []
        for index, raw_check in enumerate(raw_checks):
            check = _require_mapping(
                raw_check,
                label=f"compatibility check {index}",
            )
            _require_exact_keys(
                check,
                _EXPECTED_CHECK_KEYS,
                label=f"compatibility check {index}",
            )
            checks.append(
                CompatibilityReplayCheck(
                    status=_require_text(
                        check.get("status"),
                        label=f"compatibility check {index} status",
                    ),
                    name=_require_text(
                        check.get("name"),
                        label=f"compatibility check {index} name",
                    ),
                    detail=_require_text(
                        check.get("detail"),
                        label=f"compatibility check {index} detail",
                    ),
                )
            )

        return cls(
            source_schema_version=SUPPORT_BUNDLE_SCHEMA_VERSION,
            source_truepanel_version=_require_text(
                source.get("truepanel_version"),
                label="truepanel_version",
            ),
            source_generated_at=_validate_generated_at(
                source.get("generated_at")
            ),
            classification=_require_text(
                compatibility.get("classification"),
                label="compatibility classification",
            ),
            installation_mode=_require_text(
                compatibility.get("installation_mode"),
                label="compatibility installation_mode",
            ),
            hardware_control=_require_text(
                compatibility.get("hardware_control"),
                label="compatibility hardware_control",
            ),
            checks=tuple(checks),
        )

    @property
    def status_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for check in self.checks:
            counts[check.status] = counts.get(check.status, 0) + 1
        return dict(sorted(counts.items()))

    def as_dict(self) -> dict[str, Any]:
        return {
            "replay_schema_version": self.replay_schema_version,
            "source_schema_version": self.source_schema_version,
            "source_truepanel_version": self.source_truepanel_version,
            "source_generated_at": self.source_generated_at,
            "classification": self.classification,
            "installation_mode": self.installation_mode,
            "hardware_control": self.hardware_control,
            "checks": [check.as_dict() for check in self.checks],
            "status_counts": self.status_counts,
            "privacy": self.privacy,
            "simulation_only": self.simulation_only,
        }

    def to_black_box_frame(
        self,
        *,
        captured_at: float,
        sequence: int = 0,
    ) -> BlackBoxFrame:
        """Create a synthetic seed frame without inventing live LCD state."""

        return BlackBoxFrame.capture(
            captured_at=captured_at,
            sequence=sequence,
            telemetry={
                "compatibility_replay": self.as_dict(),
            },
            mission_control={
                "compatibility_replay": {
                    "available": True,
                    "source": "support_bundle",
                    "simulation_only": True,
                }
            },
        )


def load_compatibility_replay_profile(
    path: str | Path,
    *,
    max_bytes: int = MAX_SUPPORT_BUNDLE_BYTES,
) -> CompatibilityReplayProfile:
    """Load one bounded JSON support bundle into a simulation-only profile."""

    source = Path(path)
    limit = max(1_024, int(max_bytes))
    size = source.stat().st_size
    if size > limit:
        raise ValueError(
            "compatibility support bundle exceeds maximum size: "
            f"{size} > {limit} bytes"
        )

    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError(
            f"invalid compatibility support bundle: {error}"
        ) from error

    return CompatibilityReplayProfile.from_support_bundle(payload)


__all__ = [
    "COMPATIBILITY_REPLAY_SCHEMA_VERSION",
    "MAX_SUPPORT_BUNDLE_BYTES",
    "CompatibilityReplayCheck",
    "CompatibilityReplayProfile",
    "load_compatibility_replay_profile",
]
