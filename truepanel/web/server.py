"""Dependency-free HTTP server for TruePanel Mission Control."""

from __future__ import annotations

import argparse
import json
import logging
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from truepanel.config.persistence import (
    ConfigurationPersistenceError,
    ConfigurationPersistenceService,
)
from truepanel.config.policy import (
    ConfigurationError,
    ConfigurationPolicyService,
)

from .snapshot import SnapshotService

LOGGER = logging.getLogger("truepanel.web")
STATIC_DIR = Path(__file__).parent / "static"


class MissionControlRequestHandler(BaseHTTPRequestHandler):
    server_version = "TruePanelMissionControl/1.1"

    @property
    def snapshot_service(self):
        return self.server.snapshot_service

    def do_GET(self):
        parsed = urlparse(self.path)
        routes = {
            "/": self._dashboard,
            "/index.html": self._dashboard,
            "/api/v1/status": self._status,
            "/api/v1/history": self._history,
            "/api/v1/capabilities": self._capabilities,
            "/api/v1/config/night-mode": self._night_mode,
            "/healthz": self._health,
        }
        handler = routes.get(parsed.path)
        if handler is None:
            self._json({"error": "not_found", "path": parsed.path}, status=HTTPStatus.NOT_FOUND)
            return
        handler(parsed)

    def do_POST(self):
        parsed = urlparse(self.path)

        if parsed.path == "/api/v1/config/night-mode/preview":
            self._night_mode_preview(parsed)
            return

        if parsed.path == "/api/v1/config/night-mode/save":
            self._night_mode_save(parsed)
            return

        self._write_blocked()

    def do_PUT(self):
        self._write_blocked()

    def do_PATCH(self):
        self._write_blocked()

    def do_DELETE(self):
        self._write_blocked()

    def _write_blocked(self):
        self._json(
            {"error": "read_only", "message": "Mission Control write operations are not enabled."},
            status=HTTPStatus.METHOD_NOT_ALLOWED,
            headers={"Allow": "GET"},
        )

    def _dashboard(self, parsed):
        del parsed
        candidate = STATIC_DIR / "index.html"
        try:
            body = candidate.read_bytes()
        except OSError:
            self._json({"error": "dashboard_unavailable"}, status=HTTPStatus.INTERNAL_SERVER_ERROR)
            return
        self._send(body, content_type="text/html; charset=utf-8")

    def _status(self, parsed):
        del parsed
        self._json(self.snapshot_service.status())

    def _history(self, parsed):
        query = parse_qs(parsed.query)
        raw_limit = query.get("limit", ["240"])[0]
        try:
            limit = int(raw_limit)
        except (TypeError, ValueError):
            limit = 240
        self._json(self.snapshot_service.history(limit=limit))

    def _capabilities(self, parsed):
        del parsed
        self._json(self.snapshot_service.capabilities())

    def _night_mode(self, parsed):
        del parsed
        service = ConfigurationPolicyService(
            self.snapshot_service.config
        )
        self._json(
            {
                "read_only": not self.server.allow_config_writes,
                "writes_enabled": self.server.allow_config_writes,
                "night_mode": service.night_mode.as_dict(),
            }
        )

    def _night_mode_preview(self, parsed):
        del parsed

        raw_length = self.headers.get("Content-Length", "0")

        try:
            content_length = int(raw_length)
        except (TypeError, ValueError):
            content_length = 0

        if content_length < 1 or content_length > 16384:
            self._json(
                {
                    "error": "invalid_request",
                    "message": "Preview body must be between 1 and 16384 bytes.",
                },
                status=HTTPStatus.BAD_REQUEST,
            )
            return

        raw_body = self.rfile.read(content_length)

        try:
            payload = json.loads(raw_body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._json(
                {
                    "error": "invalid_json",
                    "message": "Preview body must contain valid JSON.",
                },
                status=HTTPStatus.BAD_REQUEST,
            )
            return

        if not isinstance(payload, dict):
            self._json(
                {
                    "error": "invalid_request",
                    "message": "Preview body must be a JSON object.",
                },
                status=HTTPStatus.BAD_REQUEST,
            )
            return

        patch = payload.get("night_mode", payload)

        if not isinstance(patch, dict):
            self._json(
                {
                    "error": "invalid_request",
                    "message": "night_mode must be a JSON object.",
                },
                status=HTTPStatus.BAD_REQUEST,
            )
            return

        service = ConfigurationPolicyService(
            self.snapshot_service.config
        )

        try:
            preview = service.preview_night_mode(patch)
        except ConfigurationError as error:
            self._json(
                {
                    "error": "configuration_rejected",
                    "message": str(error),
                },
                status=HTTPStatus.UNPROCESSABLE_ENTITY,
            )
            return

        self._json(
            {
                "read_only": True,
                "persisted": False,
                "preview": preview.as_dict(),
            }
        )

    def _night_mode_save(self, parsed):
        del parsed

        if not self.server.allow_config_writes:
            self._json(
                {
                    "error": "configuration_writes_disabled",
                    "message": (
                        "Configuration writes require "
                        "--allow-config-writes."
                    ),
                },
                status=HTTPStatus.FORBIDDEN,
            )
            return

        raw_length = self.headers.get("Content-Length", "0")

        try:
            content_length = int(raw_length)
        except (TypeError, ValueError):
            content_length = 0

        if content_length < 1 or content_length > 16384:
            self._json(
                {
                    "error": "invalid_request",
                    "message": (
                        "Save body must be between "
                        "1 and 16384 bytes."
                    ),
                },
                status=HTTPStatus.BAD_REQUEST,
            )
            return

        raw_body = self.rfile.read(content_length)

        try:
            payload = json.loads(raw_body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._json(
                {
                    "error": "invalid_json",
                    "message": "Save body must contain valid JSON.",
                },
                status=HTTPStatus.BAD_REQUEST,
            )
            return

        if not isinstance(payload, dict):
            self._json(
                {
                    "error": "invalid_request",
                    "message": "Save body must be a JSON object.",
                },
                status=HTTPStatus.BAD_REQUEST,
            )
            return

        patch = payload.get("night_mode")
        dry_run = payload.get("dry_run", False)

        if not isinstance(patch, dict):
            self._json(
                {
                    "error": "invalid_request",
                    "message": "night_mode must be a JSON object.",
                },
                status=HTTPStatus.BAD_REQUEST,
            )
            return

        if not isinstance(dry_run, bool):
            self._json(
                {
                    "error": "invalid_request",
                    "message": "dry_run must be boolean.",
                },
                status=HTTPStatus.BAD_REQUEST,
            )
            return

        service = ConfigurationPersistenceService(
            self.server.config_path,
            self.snapshot_service.config,
        )

        try:
            result = service.save_night_mode(
                patch,
                dry_run=dry_run,
            )
        except ConfigurationError as error:
            self._json(
                {
                    "error": "configuration_rejected",
                    "message": str(error),
                },
                status=HTTPStatus.UNPROCESSABLE_ENTITY,
            )
            return
        except ConfigurationPersistenceError as error:
            self._json(
                {
                    "error": "configuration_persistence_failed",
                    "message": str(error),
                },
                status=HTTPStatus.INTERNAL_SERVER_ERROR,
            )
            return

        if result.persisted:
            self.snapshot_service.config = result.proposed

        response = result.as_dict()
        response.update(
            {
                "restart_required": bool(
                    result.persisted and result.changed
                ),
                "restart_performed": False,
                "writes_enabled": True,
            }
        )
        self._json(response)

    def _health(self, parsed):
        del parsed
        self._json({"status": "ok", "service": "truepanel-mission-control", "read_only": True})

    def _json(self, payload, status=HTTPStatus.OK, headers=None):
        body = json.dumps(payload, indent=2, sort_keys=True, default=str).encode("utf-8")
        self._send(body, status=status, content_type="application/json; charset=utf-8", headers=headers)

    def _send(self, body, status=HTTPStatus.OK, content_type="application/octet-stream", headers=None):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        LOGGER.info("%s - %s", self.address_string(), format % args)


class MissionControlServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(
        self,
        address,
        snapshot_service=None,
        *,
        allow_config_writes=False,
        config_path="truepanel.yaml",
    ):
        self.snapshot_service = snapshot_service or SnapshotService()
        self.allow_config_writes = bool(allow_config_writes)
        self.config_path = Path(config_path)
        super().__init__(address, MissionControlRequestHandler)


def serve(
    host="127.0.0.1",
    port=8787,
    snapshot_service=None,
    *,
    allow_config_writes=False,
    config_path="truepanel.yaml",
):
    server = MissionControlServer(
        (host, int(port)),
        snapshot_service=snapshot_service,
        allow_config_writes=allow_config_writes,
        config_path=config_path,
    )
    LOGGER.info("Mission Control listening on http://%s:%s", host, port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def build_parser():
    parser = argparse.ArgumentParser(description="Run the read-only TruePanel Mission Control dashboard")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument(
        "--allow-config-writes",
        action="store_true",
        help=(
            "Enable guarded configuration persistence. "
            "Disabled by default."
        ),
    )
    parser.add_argument(
        "--config-path",
        default="truepanel.yaml",
        help="Configuration file used for guarded writes.",
    )
    return parser


def main():
    args = build_parser().parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    serve(
        host=args.host,
        port=args.port,
        allow_config_writes=args.allow_config_writes,
        config_path=args.config_path,
    )


if __name__ == "__main__":
    main()
