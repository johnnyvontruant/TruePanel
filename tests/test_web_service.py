from pathlib import Path

import pytest

from truepanel.web.service import (
    MissionControlServiceSettings,
    ServiceConfigurationError,
)


def test_service_defaults_are_local_and_read_only():
    settings = (
        MissionControlServiceSettings
        .from_environment({})
    )

    assert settings.host == "127.0.0.1"
    assert settings.port == 8787
    assert settings.config_path == Path(
        "/opt/truepanel/truepanel.yaml"
    )
    assert settings.allow_config_writes is False


def test_service_accepts_deliberate_lan_binding():
    settings = (
        MissionControlServiceSettings
        .from_environment(
            {
                "TRUEPANEL_MC_HOST": "0.0.0.0",
                "TRUEPANEL_MC_PORT": "9876",
            }
        )
    )

    assert settings.host == "0.0.0.0"
    assert settings.port == 9876


@pytest.mark.parametrize(
    "value",
    ["1", "true", "yes", "on"],
)
def test_service_requires_explicit_write_enable(value):
    settings = (
        MissionControlServiceSettings
        .from_environment(
            {
                "TRUEPANEL_MC_ALLOW_CONFIG_WRITES": value,
            }
        )
    )

    assert settings.allow_config_writes is True


@pytest.mark.parametrize(
    "value",
    ["0", "false", "no", "off"],
)
def test_service_keeps_writes_disabled(value):
    settings = (
        MissionControlServiceSettings
        .from_environment(
            {
                "TRUEPANEL_MC_ALLOW_CONFIG_WRITES": value,
            }
        )
    )

    assert settings.allow_config_writes is False


def test_service_rejects_invalid_port():
    with pytest.raises(
        ServiceConfigurationError,
        match="between 1 and 65535",
    ):
        (
            MissionControlServiceSettings
            .from_environment(
                {
                    "TRUEPANEL_MC_PORT": "70000",
                }
            )
        )


def test_service_rejects_ambiguous_write_setting():
    with pytest.raises(
        ServiceConfigurationError,
        match="must be boolean",
    ):
        (
            MissionControlServiceSettings
            .from_environment(
                {
                    "TRUEPANEL_MC_ALLOW_CONFIG_WRITES": "maybe",
                }
            )
        )
