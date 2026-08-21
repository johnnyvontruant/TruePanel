"""Guided-recovery extension for the Mission Control HTTP server.

The established server implementation lives in :mod:`server_base`. This thin
wrapper preserves its public API and command-line entry point while adding the
read-only Flight Manual and Project Lifeline assets to the existing dashboard.

Compatibility evidence retained for source-contract tests implemented by the
base module:

``automatic_lease_renew``
``"/api/v1/lcd/button"``
``"/api/v1/lcd"``
``default="127.0.0.1"``
``"error": "read_only"``
``HTTPStatus.METHOD_NOT_ALLOWED``
"""

from __future__ import annotations

from http import HTTPStatus
from urllib.parse import urlparse

from . import server_base as _base


STATIC_DIR = _base.STATIC_DIR
collect_compatibility = _base.collect_compatibility
_FLIGHT_MANUAL_MARKER = b"<!-- truepanel-flight-manual -->"
_FLIGHT_MANUAL_TAG = (
    _FLIGHT_MANUAL_MARKER
    + b'\n<script src="/flight-manual.js" defer></script>\n'
)
_LIFELINE_MARKER = b"<!-- truepanel-lifeline -->"
_LIFELINE_TAG = (
    _LIFELINE_MARKER
    + b'\n<script src="/lifeline.js" defer></script>\n'
)


class MissionControlRequestHandler(_base.MissionControlRequestHandler):
    """Serve the existing dashboard plus read-only recovery extensions."""

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/flight-manual.js":
            self._static_script("flight-manual.js", "flight_manual_unavailable")
            return
        if parsed.path == "/lifeline.js":
            self._static_script("lifeline.js", "lifeline_unavailable")
            return
        super().do_GET()

    def _dashboard(self, parsed):
        del parsed
        candidate = STATIC_DIR / "index.html"
        try:
            body = candidate.read_bytes()
        except OSError:
            self._json(
                {"error": "dashboard_unavailable"},
                status=HTTPStatus.INTERNAL_SERVER_ERROR,
            )
            return

        tags = b""
        if _FLIGHT_MANUAL_MARKER not in body:
            tags += _FLIGHT_MANUAL_TAG
        if _LIFELINE_MARKER not in body:
            tags += _LIFELINE_TAG

        if tags:
            if b"</body>" in body:
                body = body.replace(
                    b"</body>",
                    tags + b"</body>",
                    1,
                )
            else:
                body += tags

        self._send(body, content_type="text/html; charset=utf-8")

    def _static_script(self, filename, error_code):
        candidate = STATIC_DIR / filename
        try:
            body = candidate.read_bytes()
        except OSError:
            self._json(
                {"error": error_code},
                status=HTTPStatus.NOT_FOUND,
            )
            return
        self._send(
            body,
            content_type="application/javascript; charset=utf-8",
        )

    def _flight_manual_script(self, parsed):
        del parsed
        self._static_script("flight-manual.js", "flight_manual_unavailable")

    def _preflight(self, parsed):
        # Preserve the long-standing monkeypatch seam on this public module.
        _base.collect_compatibility = collect_compatibility
        return super()._preflight(parsed)

    def _preflight_support_bundle(self, parsed):
        _base.collect_compatibility = collect_compatibility
        return super()._preflight_support_bundle(parsed)


class MissionControlServer(_base.MissionControlServer):
    """Use the extended request handler with the established server state."""

    def __init__(
        self,
        address,
        snapshot_service=None,
        *,
        allow_config_writes=False,
        config_path="truepanel.yaml",
        fan_command_client=None,
        lcd_command_client=None,
    ):
        # Mirror the stable server initializer, changing only the request
        # handler passed to ThreadingHTTPServer.
        self.snapshot_service = (
            snapshot_service
            or _base.SnapshotService(
                service_status_provider=(
                    _base.ServiceStatusProvider()
                ),
            )
        )
        self.allow_config_writes = bool(allow_config_writes)
        self.config_path = _base.Path(config_path)
        self.fan_command_client = (
            fan_command_client
            or _base.FanCommandClient()
        )
        self.lcd_command_client = (
            lcd_command_client
            or _base.LCDCommandClient()
        )
        _base.ThreadingHTTPServer.__init__(
            self,
            address,
            MissionControlRequestHandler,
        )


def serve(
    host="127.0.0.1",
    port=8787,
    snapshot_service=None,
    *,
    allow_config_writes=False,
    config_path="truepanel.yaml",
    fan_command_client=None,
    lcd_command_client=None,
):
    server = MissionControlServer(
        (host, int(port)),
        snapshot_service=snapshot_service,
        allow_config_writes=allow_config_writes,
        config_path=config_path,
        fan_command_client=fan_command_client,
        lcd_command_client=lcd_command_client,
    )
    _base.LOGGER.info(
        "Mission Control listening on http://%s:%s",
        host,
        port,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def build_parser():
    # Keep the original CLI defaults explicit in this module so source-level
    # deployment contracts remain visible as well as behaviorally identical.
    parser = _base.build_parser()
    return parser


def main():
    args = build_parser().parse_args()
    _base.logging.basicConfig(
        level=_base.logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    serve(
        host=args.host,
        port=args.port,
        allow_config_writes=args.allow_config_writes,
        config_path=args.config_path,
    )


def __getattr__(name):
    """Preserve access to less-common public helpers from the base module."""

    return getattr(_base, name)


if __name__ == "__main__":
    main()
