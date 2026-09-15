"""Production launcher for the TruePanel Mission Control service."""

from __future__ import annotations

import logging
import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from truepanel.activity.runtime import activity_providers_from_environment
from truepanel.config.loader import load_config
from truepanel.paths import installation_root
from truepanel.wingman.runtime import (
    LlamaRuntimeConfig,
    WingmanLocalRuntime,
)
from truepanel.wingman.runtime_advisory import WingmanRuntimeAdvisory
from truepanel.wingman.web import WingmanBriefService

from .observatory_snapshot import ObservatorySnapshotService
from .pathfinder_server import serve


class ServiceConfigurationError(ValueError):
    """Raised when Mission Control service settings are invalid."""


@dataclass(frozen=True)
class WingmanServiceSettings:
    """Explicit opt-in settings for on-demand local WINGMAN inference."""

    enabled: bool = False
    server_path: Path | None = None
    model_path: Path | None = None

    @classmethod
    def from_environment(
        cls,
        environment: Mapping[str, str] | None = None,
    ):
        values = environment or os.environ

        raw_enabled = values.get(
            "TRUEPANEL_WINGMAN_ENABLED",
            "false",
        ).strip().lower()

        if raw_enabled not in {
            "0",
            "1",
            "false",
            "true",
            "no",
            "yes",
            "off",
            "on",
        }:
            raise ServiceConfigurationError(
                "TRUEPANEL_WINGMAN_ENABLED must be boolean."
            )

        enabled = raw_enabled in {
            "1",
            "true",
            "yes",
            "on",
        }

        if not enabled:
            return cls(enabled=False)

        raw_server = values.get(
            "TRUEPANEL_WINGMAN_SERVER",
            "",
        ).strip()

        raw_model = values.get(
            "TRUEPANEL_WINGMAN_MODEL",
            "",
        ).strip()

        if not raw_server:
            raise ServiceConfigurationError(
                "TRUEPANEL_WINGMAN_SERVER is required when WINGMAN is enabled."
            )

        if not raw_model:
            raise ServiceConfigurationError(
                "TRUEPANEL_WINGMAN_MODEL is required when WINGMAN is enabled."
            )

        return cls(
            enabled=True,
            server_path=Path(raw_server).expanduser().resolve(),
            model_path=Path(raw_model).expanduser().resolve(),
        )


def build_wingman_brief_service(
    settings: WingmanServiceSettings,
) -> WingmanBriefService | None:
    """Build the dormant on-demand WINGMAN stack when explicitly enabled."""

    if not settings.enabled:
        return None

    if settings.server_path is None or settings.model_path is None:
        raise ServiceConfigurationError(
            "enabled WINGMAN settings require server and model paths."
        )

    runtime = WingmanLocalRuntime(
        LlamaRuntimeConfig(
            server_path=settings.server_path,
            model_path=settings.model_path,
        )
    )

    advisory = WingmanRuntimeAdvisory(runtime)

    return WingmanBriefService(
        advisory,
        docs_root=installation_root() / "docs",
    )


@dataclass(frozen=True)
class MissionControlServiceSettings:
    host: str = "127.0.0.1"
    port: int = 8787
    config_path: Path = installation_root() / "truepanel.yaml"
    allow_config_writes: bool = False

    @classmethod
    def from_environment(
        cls,
        environment: Mapping[str, str] | None = None,
    ):
        values = environment or os.environ

        host = values.get(
            "TRUEPANEL_MC_HOST",
            "127.0.0.1",
        ).strip()

        if not host:
            raise ServiceConfigurationError(
                "TRUEPANEL_MC_HOST cannot be empty."
            )

        raw_port = values.get(
            "TRUEPANEL_MC_PORT",
            "8787",
        ).strip()

        try:
            port = int(raw_port)
        except ValueError as error:
            raise ServiceConfigurationError(
                "TRUEPANEL_MC_PORT must be an integer."
            ) from error

        if port < 1 or port > 65535:
            raise ServiceConfigurationError(
                "TRUEPANEL_MC_PORT must be between 1 and 65535."
            )

        raw_path = values.get(
            "TRUEPANEL_MC_CONFIG_PATH",
            str(
                installation_root()
                / "truepanel.yaml"
            ),
        ).strip()

        if not raw_path:
            raise ServiceConfigurationError(
                "TRUEPANEL_MC_CONFIG_PATH cannot be empty."
            )

        raw_writes = values.get(
            "TRUEPANEL_MC_ALLOW_CONFIG_WRITES",
            "false",
        ).strip().lower()

        if raw_writes not in {
            "0",
            "1",
            "false",
            "true",
            "no",
            "yes",
            "off",
            "on",
        }:
            raise ServiceConfigurationError(
                "TRUEPANEL_MC_ALLOW_CONFIG_WRITES must be boolean."
            )

        allow_config_writes = raw_writes in {
            "1",
            "true",
            "yes",
            "on",
        }

        return cls(
            host=host,
            port=port,
            config_path=Path(raw_path),
            allow_config_writes=allow_config_writes,
        )


def main():
    logging.basicConfig(
        level=logging.INFO,
        format=(
            "%(asctime)s %(levelname)s "
            "%(name)s: %(message)s"
        ),
    )

    settings = (
        MissionControlServiceSettings
        .from_environment()
    )

    wingman_settings = (
        WingmanServiceSettings
        .from_environment()
    )

    wingman_brief_service = build_wingman_brief_service(
        wingman_settings
    )

    snapshot_service = ObservatorySnapshotService(
        config=load_config(settings.config_path),
        activity_providers=activity_providers_from_environment(),
    )

    serve(
        host=settings.host,
        port=settings.port,
        allow_config_writes=(
            settings.allow_config_writes
        ),
        config_path=settings.config_path,
        snapshot_service=snapshot_service,
        wingman_brief_service=wingman_brief_service,
    )


if __name__ == "__main__":
    main()
