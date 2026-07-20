import pytest

from truepanel.config.policy import (
    ConfigurationError,
    ConfigurationPolicyService,
    NightModePolicy,
)


def test_policy_reads_existing_nested_configuration():
    policy = NightModePolicy.from_config(
        {
            "flightdeck": {
                "night_mode": {
                    "enabled": True,
                    "idle_after": 1800,
                    "rotation_interval": 60,
                    "suppress_info": True,
                    "dashboard_pages": ["home", "storage"],
                }
            }
        }
    )

    assert policy.enabled is True
    assert policy.idle_after == 1800
    assert policy.dashboard_pages == ("home", "storage")
    assert policy.backlight_off is True
    assert policy.allow_critical_alerts is True


def test_policy_rejects_unsafe_critical_alert_suppression():
    with pytest.raises(
        ConfigurationError,
        match="allow_critical_alerts",
    ):
        NightModePolicy.from_config(
            {
                "night_mode": {
                    "allow_critical_alerts": False,
                }
            }
        )


def test_policy_rejects_invalid_timing():
    with pytest.raises(
        ConfigurationError,
        match="idle_after",
    ):
        NightModePolicy.from_config(
            {
                "night_mode": {
                    "idle_after": 10,
                }
            }
        )


def test_preview_does_not_mutate_current_policy():
    service = ConfigurationPolicyService(
        {
            "flightdeck": {
                "night_mode": {
                    "idle_after": 1800,
                }
            }
        }
    )

    preview = service.preview_night_mode(
        {
            "idle_after": 3600,
            "backlight_off": False,
        }
    )

    assert preview.changed is True
    assert preview.changed_fields == (
        "idle_after",
        "backlight_off",
    )
    assert preview.current.idle_after == 1800
    assert preview.proposed.idle_after == 3600
    assert preview.current.backlight_off is True
    assert preview.proposed.backlight_off is False


def test_preview_rejects_unknown_fields():
    service = ConfigurationPolicyService({})

    with pytest.raises(
        ConfigurationError,
        match="Unknown night-mode settings",
    ):
        service.preview_night_mode(
            {
                "warp_core": True,
            }
        )


def test_policy_serializes_dashboard_pages_as_list():
    payload = NightModePolicy().as_dict()

    assert payload["dashboard_pages"] == [
        "home",
        "storage",
    ]
