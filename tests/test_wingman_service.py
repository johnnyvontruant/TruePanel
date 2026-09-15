from __future__ import annotations

from pathlib import Path

import pytest

from truepanel.web.service import (
    ServiceConfigurationError,
    WingmanServiceSettings,
    build_wingman_brief_service,
)


def test_wingman_is_disabled_by_default():
    settings = WingmanServiceSettings.from_environment({})

    assert settings.enabled is False
    assert settings.server_path is None
    assert settings.model_path is None
    assert build_wingman_brief_service(settings) is None


@pytest.mark.parametrize(
    "value",
    ("1", "true", "yes", "on"),
)
def test_wingman_explicit_enable_requires_paths(value):
    with pytest.raises(
        ServiceConfigurationError,
        match="TRUEPANEL_WINGMAN_SERVER",
    ):
        WingmanServiceSettings.from_environment(
            {
                "TRUEPANEL_WINGMAN_ENABLED": value,
            }
        )


def test_wingman_enabled_requires_model_path(tmp_path: Path):
    server = tmp_path / "llama-server"

    with pytest.raises(
        ServiceConfigurationError,
        match="TRUEPANEL_WINGMAN_MODEL",
    ):
        WingmanServiceSettings.from_environment(
            {
                "TRUEPANEL_WINGMAN_ENABLED": "true",
                "TRUEPANEL_WINGMAN_SERVER": str(server),
            }
        )


def test_wingman_enabled_builds_dormant_loopback_runtime(
    tmp_path: Path,
):
    server = tmp_path / "llama-server"
    model = tmp_path / "granite.gguf"

    settings = WingmanServiceSettings.from_environment(
        {
            "TRUEPANEL_WINGMAN_ENABLED": "true",
            "TRUEPANEL_WINGMAN_SERVER": str(server),
            "TRUEPANEL_WINGMAN_MODEL": str(model),
        }
    )

    service = build_wingman_brief_service(settings)

    assert service is not None

    runtime = service.advisory.runtime

    assert runtime.running is False
    assert runtime.config.server_path == server.resolve()
    assert runtime.config.model_path == model.resolve()
    assert runtime.config.host == "127.0.0.1"
    assert runtime.config.port == 18080
    assert runtime.config.context_size == 4096
    assert runtime.config.threads == 4
    assert runtime.config.parallel == 1

    assert (
        runtime.policy.minimum_available_memory_bytes
        == 3 * 1024**3
    )
    assert runtime.policy.maximum_load_1m == 6.0


def test_invalid_wingman_boolean_fails_closed():
    with pytest.raises(
        ServiceConfigurationError,
        match="TRUEPANEL_WINGMAN_ENABLED",
    ):
        WingmanServiceSettings.from_environment(
            {
                "TRUEPANEL_WINGMAN_ENABLED": "maybe",
            }
        )
