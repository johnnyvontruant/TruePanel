"""Dependency-free HTTP server for TruePanel Mission Control."""

from __future__ import annotations

import argparse
import json
import logging
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

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
            "/healthz": self._health,
        }
        handler = routes.get(parsed.path)
        if handler is None:
            self._json({"error": "not_found", "path": parsed.path}, status=HTTPStatus.NOT_FOUND)
            return
        handler(parsed)

    def do_POST(self):
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

    def __init__(self, address, snapshot_service=None):
        self.snapshot_service = snapshot_service or SnapshotService()
        super().__init__(address, MissionControlRequestHandler)


def serve(host="127.0.0.1", port=8787, snapshot_service=None):
    server = MissionControlServer((host, int(port)), snapshot_service=snapshot_service)
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
    return parser


def main():
    args = build_parser().parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    serve(host=args.host, port=args.port)


if __name__ == "__main__":
    main()
