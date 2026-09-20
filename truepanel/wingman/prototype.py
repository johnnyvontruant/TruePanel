"""Isolated, opt-in Mission Control prototype for Project WINGMAN.

This entry point is deliberately separate from the production Mission Control
entry point. It serves a loopback-only experimental cockpit on another port.
Only the WINGMAN brief POST is enabled; all other POST endpoints are denied.
"""

from __future__ import annotations

import argparse
import logging
from http import HTTPStatus
from pathlib import Path
from urllib.parse import urlparse

from truepanel.web.pathfinder_server import (
    MissionControlRequestHandler,
    MissionControlServer,
)

from .offline import offline_brief
from .readiness import file_availability, inference_readiness
from .runtime import LlamaRuntimeConfig, WingmanLocalRuntime
from .runtime_advisory import WingmanRuntimeAdvisory
from .web import WingmanBriefService

LOGGER = logging.getLogger(__name__)
PROTOTYPE_PORT = 18787
PRODUCTION_PORT = 8787


class WingmanPrototypeHandler(MissionControlRequestHandler):
    """Permit brief generation without exposing other mutation endpoints."""

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/api/v1/wingman/offline-brief":
            try:
                snapshot = self.snapshot_service.status()
                self._json(offline_brief(snapshot))
            except (OSError, RuntimeError, TypeError, ValueError, AttributeError):
                self._json(offline_brief({}))
            return
        if path == "/api/v1/wingman/readiness":
            runtime = self.server.wingman_brief_service.advisory.runtime
            try:
                resources = runtime._resource_reader()
            except (OSError, RuntimeError, TypeError, ValueError):
                resources = None
            try:
                files = file_availability(
                    runtime.config.server_path, runtime.config.model_path
                )
            except (OSError, RuntimeError, TypeError, ValueError):
                from .readiness import FileAvailability

                files = FileAvailability(
                    server_present=False, model_present=False
                )
            self._json(inference_readiness(resources, files, runtime.policy))
            return
        return super().do_GET()

    def do_POST(self):
        if urlparse(self.path).path == "/api/v1/wingman/brief":
            return super().do_POST()
        self._json(
            {
                "error": "wingman_prototype_read_only",
                "message": "Only the WINGMAN brief POST is enabled in this prototype.",
            },
            status=HTTPStatus.FORBIDDEN,
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run a loopback-only WINGMAN experimental cockpit."
    )
    parser.add_argument(
        "--llama-server",
        type=Path,
        required=True,
        help="Path to the local llama-server executable.",
    )
    parser.add_argument(
        "--model",
        type=Path,
        required=True,
        help="Path to the local GGUF model; never downloaded automatically.",
    )
    parser.add_argument(
        "--docs-root",
        type=Path,
        required=True,
        help="Path to the checked-out TruePanel docs directory.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=PROTOTYPE_PORT,
        help="Isolated loopback cockpit port (default: 18787).",
    )
    return parser


def validate_options(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    """Reject missing resources and accidental production-port use before bind."""

    if args.port == PRODUCTION_PORT or not (1024 <= args.port <= 65535):
        parser.error("prototype port must be 1024-65535 and must not be 8787")
    if not args.llama_server.is_file():
        parser.error("local llama-server executable does not exist")
    if not args.model.is_file():
        parser.error("local GGUF model does not exist")
    if not args.docs_root.is_dir():
        parser.error("TruePanel docs directory does not exist")


def build_brief_service(
    *, llama_server: Path, model: Path, docs_root: Path
) -> WingmanBriefService:
    """Wire the existing bounded runtime to the existing grounded brief."""

    runtime = WingmanLocalRuntime(
        LlamaRuntimeConfig(
            server_path=llama_server,
            model_path=model,
        )
    )
    return WingmanBriefService(
        WingmanRuntimeAdvisory(runtime),
        docs_root=docs_root,
    )


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    validate_options(args, parser)
    advisory = build_brief_service(
        llama_server=args.llama_server,
        model=args.model,
        docs_root=args.docs_root,
    )
    logging.basicConfig(level=logging.INFO)
    server = MissionControlServer(
        ("127.0.0.1", args.port),
        allow_config_writes=False,
        wingman_brief_service=advisory,
    )
    server.RequestHandlerClass = WingmanPrototypeHandler
    LOGGER.info("WINGMAN prototype listening on http://127.0.0.1:%s", args.port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
