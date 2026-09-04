"""Read-only WATCHTOWER presentation layer for Mission Control."""

from __future__ import annotations

from urllib.parse import urlparse

from . import pathfinder_server as _pathfinder

STATIC_DIR = _pathfinder.STATIC_DIR
_WATCHTOWER_SCRIPT = "watchtower.js"
_WATCHTOWER_MARKER = b"<!-- truepanel-watchtower -->"
_WATCHTOWER_TAG = _WATCHTOWER_MARKER + b'\n<script src="/watchtower.js" defer></script>\n'


class MissionControlRequestHandler(_pathfinder.MissionControlRequestHandler):
    """Serve the WATCHTOWER UI without adding mutation routes."""

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == f"/{_WATCHTOWER_SCRIPT}":
            self._static_script(_WATCHTOWER_SCRIPT, "watchtower_unavailable")
            return
        super().do_GET()

    def _dashboard(self, parsed):
        del parsed
        candidate = STATIC_DIR / "index.html"
        try:
            body = candidate.read_bytes()
        except OSError:
            return super()._dashboard(None)

        if _WATCHTOWER_MARKER not in body:
            if b"</body>" in body:
                body = body.replace(b"</body>", _WATCHTOWER_TAG + b"</body>", 1)
            else:
                body += _WATCHTOWER_TAG

        # Reuse Pathfinder's complete additive dashboard composition by
        # temporarily presenting the WATCHTOWER-enriched body as the static
        # dashboard is deliberately avoided. Instead reproduce its tags here.
        tags = b""
        inherited = (
            (_pathfinder._server._FLIGHT_MANUAL_MARKER, _pathfinder._server._FLIGHT_MANUAL_TAG),
            (_pathfinder._server._COCKPIT_POLISH_MARKER, _pathfinder._server._COCKPIT_POLISH_TAG),
            (_pathfinder._server._GLASS_COCKPIT_MARKER, _pathfinder._server._GLASS_COCKPIT_TAG),
            (_pathfinder._server._COCKPIT_VARIANTS_MARKER, _pathfinder._server._COCKPIT_VARIANTS_TAG),
            (_pathfinder._server._LIFELINE_MARKER, _pathfinder._server._LIFELINE_TAG),
            (_pathfinder._server._LIFELINE_ACTIONS_MARKER, _pathfinder._server._LIFELINE_ACTIONS_TAG),
            (_pathfinder._RECOVERY_MARKER, _pathfinder._RECOVERY_TAG),
            (_pathfinder._RELIABILITY_MARKER, _pathfinder._RELIABILITY_TAG),
            (_pathfinder._THEME_TOGGLE_SYNC_MARKER, _pathfinder._THEME_TOGGLE_SYNC_TAG),
        )
        if _pathfinder._THEME_BOOTSTRAP_MARKER not in body:
            if b"</head>" in body:
                body = body.replace(b"</head>", _pathfinder._THEME_BOOTSTRAP_TAG + b"</head>", 1)
            else:
                body = _pathfinder._THEME_BOOTSTRAP_TAG + body
        for marker, tag in inherited:
            if marker not in body:
                tags += tag
        if tags:
            body = body.replace(b"</body>", tags + b"</body>", 1) if b"</body>" in body else body + tags
        self._send(body, content_type="text/html; charset=utf-8")


class MissionControlServer(_pathfinder.MissionControlServer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.RequestHandlerClass = MissionControlRequestHandler


def serve(
    host="127.0.0.1",
    port=8787,
    snapshot_service=None,
    *,
    allow_config_writes=False,
    config_path="truepanel.yaml",
    fan_command_client=None,
    lcd_command_client=None,
    lifeline_identify_service=None,
    bay_mirror_provider=None,
    recovery_session_store=None,
):
    server = MissionControlServer(
        (host, int(port)),
        snapshot_service=snapshot_service,
        allow_config_writes=allow_config_writes,
        config_path=config_path,
        fan_command_client=fan_command_client,
        lcd_command_client=lcd_command_client,
        lifeline_identify_service=lifeline_identify_service,
        bay_mirror_provider=bay_mirror_provider,
        recovery_session_store=recovery_session_store,
    )
    _pathfinder._server._base.LOGGER.info("Mission Control listening on http://%s:%s", host, port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


__all__ = ["MissionControlRequestHandler", "MissionControlServer", "serve"]
