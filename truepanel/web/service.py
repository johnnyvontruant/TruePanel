"""Production launcher for the TruePanel Mission Control service."""

from __future__ import annotations

import logging
import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from truepanel.activity.runtime import activity_providers_from_environment
from truepanel.health import ServiceStatusProvider
from truepanel.paths import installation_root

from .observatory_snapshot import ObservatorySnapshotService
from .pathfinder_server import serve


class ServiceConfigurationError(ValueError):
    """Raised when Mission Control service settings are invalid."""


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
    snapshot_service = ObservatorySnapshotService(
        service_status_provider=ServiceStatusProvider(),
        config_path=settings.config_path,
        activity_providers=activity_providers_from_environment(),
    )

    serve(
        host=settings.host,
        port=settings.port,
        snapshot_service=snapshot_service,
        allow_config_writes=(
            settings.allow_config_writes
        ),
        config_path=settings.config_path,
    )


if __name__ == "__main__":
    main()
