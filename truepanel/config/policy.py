"""Validated configuration policy for TruePanel night mode."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping


class ConfigurationError(ValueError):
    """Raised when a configuration update violates policy."""


@dataclass(frozen=True)
class NightModePolicy:
    enabled: bool = True
    idle_after: int = 1800
    rotation_interval: int = 60
    suppress_info: bool = True
    dashboard_pages: tuple[str, ...] = ("home", "storage")
    backlight_off: bool = True
    wake_on_button: bool = True
    allow_warning_alerts: bool = True
    allow_critical_alerts: bool = True

    @classmethod
    def from_config(
        cls,
        config: Mapping[str, Any] | None,
    ) -> "NightModePolicy":
        root = dict(config or {})
        flightdeck = root.get("flightdeck", root)
        section = dict(flightdeck.get("night_mode", {}))
        defaults = cls()

        pages = section.get(
            "dashboard_pages",
            defaults.dashboard_pages,
        )

        if isinstance(pages, str):
            raise ConfigurationError(
                "night_mode.dashboard_pages must be a list"
            )

        policy = cls(
            enabled=section.get("enabled", defaults.enabled),
            idle_after=section.get(
                "idle_after",
                defaults.idle_after,
            ),
            rotation_interval=section.get(
                "rotation_interval",
                defaults.rotation_interval,
            ),
            suppress_info=section.get(
                "suppress_info",
                defaults.suppress_info,
            ),
            dashboard_pages=tuple(pages),
            backlight_off=section.get(
                "backlight_off",
                defaults.backlight_off,
            ),
            wake_on_button=section.get(
                "wake_on_button",
                defaults.wake_on_button,
            ),
            allow_warning_alerts=section.get(
                "allow_warning_alerts",
                defaults.allow_warning_alerts,
            ),
            allow_critical_alerts=section.get(
                "allow_critical_alerts",
                defaults.allow_critical_alerts,
            ),
        )

        policy.validate()
        return policy

    def validate(self) -> None:
        boolean_fields = (
            "enabled",
            "suppress_info",
            "backlight_off",
            "wake_on_button",
            "allow_warning_alerts",
            "allow_critical_alerts",
        )

        for field_name in boolean_fields:
            if not isinstance(getattr(self, field_name), bool):
                raise ConfigurationError(
                    f"night_mode.{field_name} must be boolean"
                )

        if not isinstance(self.idle_after, int):
            raise ConfigurationError(
                "night_mode.idle_after must be an integer"
            )

        if not 60 <= self.idle_after <= 86400:
            raise ConfigurationError(
                "night_mode.idle_after must be between 60 and 86400 seconds"
            )

        if not isinstance(self.rotation_interval, int):
            raise ConfigurationError(
                "night_mode.rotation_interval must be an integer"
            )

        if not 5 <= self.rotation_interval <= 3600:
            raise ConfigurationError(
                "night_mode.rotation_interval must be between 5 and 3600 seconds"
            )

        if not self.dashboard_pages:
            raise ConfigurationError(
                "night_mode.dashboard_pages must not be empty"
            )

        for page in self.dashboard_pages:
            if not isinstance(page, str) or not page.strip():
                raise ConfigurationError(
                    "night_mode.dashboard_pages entries must be non-empty strings"
                )

        if not self.allow_critical_alerts:
            raise ConfigurationError(
                "night_mode.allow_critical_alerts cannot be disabled"
            )

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["dashboard_pages"] = list(self.dashboard_pages)
        return payload

    def apply_patch(
        self,
        patch: Mapping[str, Any],
    ) -> "NightModePolicy":
        unknown = set(patch) - set(self.as_dict())

        if unknown:
            names = ", ".join(sorted(unknown))
            raise ConfigurationError(
                f"Unknown night-mode settings: {names}"
            )

        merged = self.as_dict()
        merged.update(dict(patch))

        return NightModePolicy.from_config(
            {"night_mode": merged}
        )


@dataclass(frozen=True)
class ConfigurationPreview:
    current: NightModePolicy
    proposed: NightModePolicy
    changed_fields: tuple[str, ...]

    @property
    def changed(self) -> bool:
        return bool(self.changed_fields)

    def as_dict(self) -> dict[str, Any]:
        return {
            "changed": self.changed,
            "changed_fields": list(self.changed_fields),
            "current": self.current.as_dict(),
            "proposed": self.proposed.as_dict(),
        }


class ConfigurationPolicyService:
    """Validate and preview configuration changes without writing files."""

    def __init__(self, config: Mapping[str, Any] | None):
        self.config = dict(config or {})
        self.night_mode = NightModePolicy.from_config(self.config)

    def preview_night_mode(
        self,
        patch: Mapping[str, Any],
    ) -> ConfigurationPreview:
        proposed = self.night_mode.apply_patch(patch)
        current_payload = self.night_mode.as_dict()
        proposed_payload = proposed.as_dict()

        changed_fields = tuple(
            key
            for key in current_payload
            if current_payload[key] != proposed_payload[key]
        )

        return ConfigurationPreview(
            current=self.night_mode,
            proposed=proposed,
            changed_fields=changed_fields,
        )
